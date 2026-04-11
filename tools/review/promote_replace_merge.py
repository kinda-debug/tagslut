#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from pathlib import Path

from mutagen.flac import FLAC

from tagslut.metadata.canon import apply_canon, load_canon_rules
from tagslut.utils.console_ui import ConsoleUI
from tagslut.utils.file_operations import FileOperations
from tagslut.utils.final_library_layout import FinalLibraryLayoutError, build_final_library_destination
from tagslut.utils.safety_gates import SafetyGates


CORE_TAGS = {
    "title",
    "artist",
    "album",
    "albumartist",
    "tracknumber",
    "discnumber",
    "date",
    "year",
    "originaldate",
    "isrc",
    "label",
    "genre",
    "bpm",
    "key",
    "musicbrainz_recordingid",
    "musicbrainz_albumid",
    "musicbrainz_artistid",
    "musicbrainz_albumartistid",
    "musicbrainz_trackid",
    "musicbrainz_releasegroupid",
}

ALWAYS_INTERESTING_PREFIXES = (
    "replaygain_",
    "r128_",
    "comment",
    "description",
    "lyrics",
    "grouping",
    "cuesheet",
    "acoustid",
    "dj",
    "dedupe_",
)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def _active_link_where(conn: sqlite3.Connection) -> str:
    if _column_exists(conn, "asset_link", "active"):
        return "al.active = 1"
    return "1=1"


def _root_like_patterns(root: Path) -> tuple[str, str]:
    root_s = str(root)
    return (root_s, root_s.rstrip("/") + "/%")


def _identity_asset_candidates_under_root(
    conn: sqlite3.Connection, root: Path
) -> dict[int, list[tuple[int, str]]]:
    if not (
        _table_exists(conn, "asset_file")
        and _table_exists(conn, "asset_link")
        and _table_exists(conn, "track_identity")
    ):
        return {}

    root_exact, root_prefix = _root_like_patterns(root)
    where_link_active = _active_link_where(conn)
    merged_where = "ti.merged_into_id IS NULL" if _column_exists(conn, "track_identity", "merged_into_id") else "1=1"
    rows = conn.execute(
        f"""
        SELECT al.identity_id AS identity_id, af.id AS asset_id, af.path AS path
        FROM asset_file af
        JOIN asset_link al ON al.asset_id = af.id
        JOIN track_identity ti ON ti.id = al.identity_id
        WHERE ({where_link_active})
          AND ({merged_where})
          AND (af.path = ? OR af.path LIKE ?)
        ORDER BY al.identity_id ASC, af.path ASC, af.id ASC
        """,
        (root_exact, root_prefix),
    ).fetchall()

    grouped: dict[int, list[tuple[int, str]]] = {}
    for row in rows:
        identity_id = int(row[0])
        grouped.setdefault(identity_id, []).append((int(row[1]), str(row[2])))
    return grouped


def _preferred_asset_by_identity(
    conn: sqlite3.Connection, identity_ids: set[int]
) -> dict[int, tuple[int, str]]:
    if not identity_ids:
        return {}
    if not (_table_exists(conn, "preferred_asset") and _table_exists(conn, "asset_file")):
        return {}
    placeholders = ",".join("?" for _ in identity_ids)
    rows = conn.execute(
        f"""
        SELECT pa.identity_id AS identity_id, pa.asset_id AS asset_id, af.path AS path
        FROM preferred_asset pa
        JOIN asset_file af ON af.id = pa.asset_id
        WHERE pa.identity_id IN ({placeholders})
        """,
        tuple(sorted(identity_ids)),
    ).fetchall()
    return {int(row[0]): (int(row[1]), str(row[2])) for row in rows}


def plan_promote_assets_for_root(
    conn: sqlite3.Connection,
    *,
    root: Path,
    use_preferred_asset: bool,
    require_preferred_asset: bool,
    allow_multiple_per_identity: bool,
) -> tuple[dict[str, dict[str, object]], dict[str, int]]:
    """Plan root-scoped promotion selection keyed by source path."""
    identity_candidates = _identity_asset_candidates_under_root(conn, root)
    if not identity_candidates:
        return {}, {"identities_scanned": 0, "selected": 0, "skipped_no_preferred": 0}

    preferred_table_exists = _table_exists(conn, "preferred_asset")
    preferred_by_identity = (
        _preferred_asset_by_identity(conn, set(identity_candidates.keys()))
        if (use_preferred_asset and preferred_table_exists)
        else {}
    )
    root_exact, root_prefix = _root_like_patterns(root)
    selected: dict[str, dict[str, object]] = {}
    skipped_no_preferred = 0

    for identity_id in sorted(identity_candidates):
        candidates = identity_candidates[identity_id]
        if allow_multiple_per_identity:
            for asset_id, path in candidates:
                selected[path] = {
                    "identity_id": identity_id,
                    "asset_id": asset_id,
                    "selection_reason": "allow_multiple_per_identity",
                    "used_preferred": 0,
                }
            continue

        chosen_asset_id: int | None = None
        chosen_path: str | None = None
        selection_reason = "fallback_under_root"
        used_preferred = 0

        preferred = preferred_by_identity.get(identity_id)
        if preferred is not None:
            pref_asset_id, pref_path = preferred
            if pref_path == root_exact or pref_path.startswith(root_prefix[:-1]):
                chosen_asset_id = pref_asset_id
                chosen_path = pref_path
                selection_reason = "preferred_under_root"
                used_preferred = 1
            else:
                selection_reason = "preferred_outside_root"
        elif use_preferred_asset and require_preferred_asset and preferred_table_exists:
            skipped_no_preferred += 1
            continue

        if chosen_asset_id is None:
            fallback_asset_id, fallback_path = min(candidates, key=lambda item: (item[1], item[0]))
            chosen_asset_id = fallback_asset_id
            chosen_path = fallback_path
            if use_preferred_asset and preferred is None and preferred_table_exists:
                selection_reason = "no_preferred_for_identity"
            elif use_preferred_asset and not preferred_table_exists:
                selection_reason = "preferred_table_missing"

        if chosen_path is None:
            continue
        selected[chosen_path] = {
            "identity_id": identity_id,
            "asset_id": chosen_asset_id,
            "selection_reason": selection_reason,
            "used_preferred": used_preferred,
        }

    return selected, {
        "identities_scanned": len(identity_candidates),
        "selected": len(selected),
        "skipped_no_preferred": skipped_no_preferred,
    }


def is_interesting(key: str) -> bool:
    lk = key.lower().strip()
    if lk in CORE_TAGS:
        return False
    return lk.startswith(ALWAYS_INTERESTING_PREFIXES) or True


def flac_test_ok(path: Path) -> tuple[bool, str | None]:
    try:
        res = subprocess.run(
            ["flac", "-t", "--silent", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, "flac binary missing"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if res.returncode == 0:
        return True, None
    err = (res.stderr or res.stdout or "").strip()
    return False, err[:400] or "flac -t failed"


def duration_ok(conn: sqlite3.Connection, src: Path) -> tuple[bool, str]:
    if not _table_exists(conn, "files"):
        return True, "duration_check_not_available"
    row = conn.execute(
        "SELECT duration_status FROM files WHERE path = ?",
        (str(src),),
    ).fetchone()
    if not row:
        return False, "duration_status=missing"
    status = (row[0] or "").strip().lower()
    if status == "ok":
        return True, "duration_status=ok"
    return False, f"duration_status={status or 'unknown'}"


def merge_old_metadata_into_new(dest_existing: Path, src_new: Path) -> tuple[int, int]:
    old = FLAC(dest_existing)
    new = FLAC(src_new)

    added_tags = 0
    added_pictures = 0

    for key, value in old.tags.items():
        if not is_interesting(key):
            continue
        if key not in new.tags:
            if isinstance(value, list):
                new.tags[key] = [str(v) for v in value]
            else:
                new.tags[key] = str(value)
            added_tags += 1

    if len(new.pictures) == 0 and len(old.pictures) > 0:
        for pic in old.pictures:
            new.add_picture(pic)
            added_pictures += 1

    if added_tags > 0 or added_pictures > 0:
        new.save()

    return added_tags, added_pictures


def choose_destination(tags: dict, src: Path, dest_root: Path) -> tuple[Path, str]:
    try:
        layout = build_final_library_destination(tags, dest_root)
        return layout.dest_path, "final_library"
    except FinalLibraryLayoutError as exc:
        fallback = dest_root / "_UNRESOLVED" / src.name
        return fallback, f"fallback_unresolved:{exc}"


def _file_quality(path: Path) -> tuple[int, int, int, int]:
    """Return (sample_rate, bit_depth, bitrate, size) for quality comparisons."""
    try:
        audio = FLAC(path)
        info = audio.info
        sample_rate = int(getattr(info, "sample_rate", 0) or 0)
        bit_depth = int(getattr(info, "bits_per_sample", 0) or 0)
        bitrate = int(getattr(info, "bitrate", 0) or 0)
    except Exception:
        sample_rate = 0
        bit_depth = 0
        bitrate = 0
    try:
        size = int(path.stat().st_size)
    except Exception:
        size = 0
    return (sample_rate, bit_depth, bitrate, size)


def db_update_path(conn: sqlite3.Connection, src: Path, dest: Path) -> int:
    """Update DB path for moved file and resolve unique-path collisions."""
    if not _table_exists(conn, "files"):
        return 0
    src_s = str(src)
    dest_s = str(dest)
    try:
        cur = conn.execute(
            """
            UPDATE files
            SET original_path = COALESCE(original_path, path),
                path = ?,
                zone = 'accepted',
                mgmt_status = 'moved_from_plan'
            WHERE path = ?
            """,
            (dest_s, src_s),
        )
        return cur.rowcount
    except sqlite3.IntegrityError:
        # Destination row already exists: preserve the new source row by replacing dest row.
        conn.execute("DELETE FROM files WHERE path = ?", (dest_s,))
        cur = conn.execute(
            """
            UPDATE files
            SET original_path = COALESCE(original_path, path),
                path = ?,
                zone = 'accepted',
                mgmt_status = 'moved_from_plan'
            WHERE path = ?
            """,
            (dest_s, src_s),
        )
        return cur.rowcount


def find_duplicate_by_hash(conn: sqlite3.Connection, src: Path, dest_root: Path) -> str | None:
    """Find an existing file in dest_root with same audio hash as src."""
    if not _table_exists(conn, "files"):
        return None
    cur = conn.execute(
        """
        SELECT sha256, streaminfo_md5, checksum
        FROM files
        WHERE path = ?
        """,
        (str(src),),
    )
    row = cur.fetchone()
    if not row:
        return None
    sha256, streaminfo_md5, checksum = row

    def _query(col: str, val: str) -> str | None:
        if not val:
            return None
        r = conn.execute(
            f"""
            SELECT path FROM files
            WHERE {col} = ? AND path != ? AND path LIKE ?
            LIMIT 1
            """,
            (val, str(src), str(dest_root) + "%"),
        ).fetchone()
        return r[0] if r else None

    # Prefer strongest hashes first
    for col, val in (("sha256", sha256), ("streaminfo_md5", streaminfo_md5), ("checksum", checksum)):
        hit = _query(col, val)
        if hit:
            return hit
    return None


def record_promotion_provenance(
    conn: sqlite3.Connection,
    *,
    identity_id: int | None,
    asset_id: int | None,
    source_path: Path,
    dest_path: Path,
    status: str,
    reason: str,
) -> None:
    if not _table_exists(conn, "provenance_event"):
        return
    details = json.dumps(
        {"selection_reason": reason, "chosen_asset_id": asset_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    conn.execute(
        """
        INSERT INTO provenance_event (
            event_type,
            asset_id,
            identity_id,
            source_path,
            dest_path,
            status,
            details_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "promotion_select",
            asset_id,
            identity_id,
            str(source_path),
            str(dest_path),
            status,
            details,
        ),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Promote tracks with collision replace + metadata merge")
    ap.add_argument("source", type=Path)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    _repo = Path(__file__).resolve().parents[2]
    ap.add_argument("--canon-rules", type=Path, default=_repo / "tools/rules/library_canon.json")
    ap.add_argument("--move-log", type=Path, default=_repo / "artifacts/logs/file_move_staging_replace.jsonl")
    ap.add_argument(
        "--allow-duplicate-hash",
        action="store_true",
        help="Allow moving files even if identical hash exists in library",
    )
    ap.add_argument(
        "--allow-non-ok-duration",
        action="store_true",
        help="Allow promotion when duration_status is not ok (default: block)",
    )
    ap.add_argument(
        "--replace-if-better",
        action="store_true",
        help="Only replace when source quality is better than destination (default: off)",
    )
    ap.add_argument(
        "--skip-flac-test",
        action="store_true",
        help="Skip flac -t integrity test (default: run and block corrupt files)",
    )
    ap.add_argument(
        "--use-preferred-asset",
        dest="use_preferred_asset",
        action="store_true",
        default=None,
        help="Use preferred_asset selection when available",
    )
    ap.add_argument(
        "--no-use-preferred-asset",
        dest="use_preferred_asset",
        action="store_false",
        help="Disable preferred_asset selection and use legacy behavior",
    )
    ap.add_argument(
        "--require-preferred-asset",
        action="store_true",
        help="Skip identities that do not have preferred asset under root",
    )
    ap.add_argument(
        "--allow-multiple-per-identity",
        action="store_true",
        help="Allow promoting multiple assets per identity (default: one per identity)",
    )
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    source = args.source.expanduser().resolve()
    dest_root = args.dest.expanduser().resolve()
    db_path = args.db.expanduser().resolve()

    files = sorted(source.rglob("*.flac"))
    if not files:
        print("No FLAC files found")
        return 0

    canon_rules = load_canon_rules(args.canon_rules)

    ui = ConsoleUI()
    gates = SafetyGates(ui=ui)
    ops = FileOperations(ui=ui, gates=gates, dry_run=not args.execute, quiet=True, audit_log_path=args.move_log)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    moved = 0
    replaced = 0
    merged_tags = 0
    merged_pictures = 0
    skipped = 0
    kept_existing = 0
    skipped_integrity = 0
    skipped_duration = 0
    errored = 0
    unresolved = 0
    dup_skipped = 0
    db_updated = 0
    selected_by_path: dict[str, dict[str, object]] = {}
    selection_mode = "legacy"
    selection_stats = {"identities_scanned": 0, "selected": 0, "skipped_no_preferred": 0}

    try:
        has_identity_mapping = (
            _table_exists(conn, "asset_file")
            and _table_exists(conn, "asset_link")
            and _table_exists(conn, "track_identity")
        )
        preferred_table_exists = _table_exists(conn, "preferred_asset")
        use_preferred_asset = (
            preferred_table_exists if args.use_preferred_asset is None else bool(args.use_preferred_asset)
        )
        if args.require_preferred_asset and not use_preferred_asset:
            print("require_preferred_asset ignored because preferred selection is disabled")
        if has_identity_mapping and not args.allow_multiple_per_identity:
            selected_by_path, selection_stats = plan_promote_assets_for_root(
                conn,
                root=source,
                use_preferred_asset=use_preferred_asset,
                require_preferred_asset=bool(args.require_preferred_asset),
                allow_multiple_per_identity=bool(args.allow_multiple_per_identity),
            )
            if use_preferred_asset and preferred_table_exists:
                selection_mode = "preferred"
            elif use_preferred_asset and not preferred_table_exists:
                selection_mode = "preferred_fallback_no_table"
            else:
                selection_mode = "identity_fallback_under_root"
        elif has_identity_mapping and args.allow_multiple_per_identity:
            selection_mode = "allow_multiple_per_identity"
        else:
            selection_mode = "legacy"

        for i, src in enumerate(files, 1):
            try:
                if has_identity_mapping and not args.allow_multiple_per_identity:
                    selected = selected_by_path.get(str(src))
                    if selected is None:
                        skipped += 1
                        continue
                else:
                    selected = selected_by_path.get(str(src))

                if not args.skip_flac_test:
                    ok, err = flac_test_ok(src)
                    if not ok:
                        skipped_integrity += 1
                        if i % 25 == 0 or i == len(files):
                            print(f"[{i}/{len(files)}] integrity_skip={skipped_integrity}")
                        continue

                if not args.allow_non_ok_duration:
                    ok, reason = duration_ok(conn, src)
                    if not ok:
                        skipped_duration += 1
                        if i % 25 == 0 or i == len(files):
                            print(f"[{i}/{len(files)}] duration_skip={skipped_duration} ({reason})")
                        continue

                audio = FLAC(src)
                raw_tags = {k: list(v) if isinstance(v, list) else v for k, v in audio.tags.items()}
                canon_tags = apply_canon(raw_tags, canon_rules)
                dest, mode = choose_destination(canon_tags, src, dest_root)

                if mode.startswith("fallback_unresolved"):
                    unresolved += 1

                if src == dest:
                    skipped += 1
                    continue

                if not args.allow_duplicate_hash:
                    dup = find_duplicate_by_hash(conn, src, dest_root)
                    if dup:
                        dup_skipped += 1
                        continue

                if args.replace_if_better and dest.exists() and dest != src:
                    dest_ok = True
                    if not args.skip_flac_test:
                        dest_ok, _ = flac_test_ok(dest)
                    if dest_ok:
                        src_q = _file_quality(src)
                        dest_q = _file_quality(dest)
                        if src_q <= dest_q:
                            kept_existing += 1
                            if i % 25 == 0 or i == len(files):
                                print(f"[{i}/{len(files)}] kept_existing={kept_existing}")
                            continue

                if args.execute and dest.exists() and dest != src:
                    tags_added, pics_added = merge_old_metadata_into_new(dest, src)
                    if tags_added or pics_added:
                        merged_tags += tags_added
                        merged_pictures += pics_added
                    replaced += 1

                ok = ops.safe_move(src, dest, skip_confirmation=True, allow_overwrite=True)
                if not ok:
                    skipped += 1
                    if args.execute and selected:
                        record_promotion_provenance(
                            conn,
                            identity_id=int(selected["identity_id"]),
                            asset_id=int(selected["asset_id"]),
                            source_path=src,
                            dest_path=dest,
                            status="skipped",
                            reason=str(selected.get("selection_reason", "legacy")),
                        )
                    continue

                moved += 1
                if args.execute:
                    db_updated += db_update_path(conn, src, dest)
                    if selected:
                        record_promotion_provenance(
                            conn,
                            identity_id=int(selected["identity_id"]),
                            asset_id=int(selected["asset_id"]),
                            source_path=src,
                            dest_path=dest,
                            status="moved",
                            reason=str(selected.get("selection_reason", "legacy")),
                        )
                if selected:
                    print(
                        "selection:"
                        f" identity_id={selected['identity_id']}"
                        f" asset_id={selected['asset_id']}"
                        f" reason={selected.get('selection_reason', 'legacy')}"
                        f" preferred={selected.get('used_preferred', 0)}"
                    )

                if i % 25 == 0 or i == len(files):
                    print(f"[{i}/{len(files)}] moved={moved} replaced={replaced} unresolved={unresolved}")
            except Exception:
                errored += 1

        if args.execute:
            conn.commit()
    finally:
        conn.close()

    print("RESULTS")
    print(f"total={len(files)}")
    print(f"moved={moved}")
    print(f"replaced={replaced}")
    print(f"merged_tags={merged_tags}")
    print(f"merged_pictures={merged_pictures}")
    print(f"db_updated={db_updated}")
    print(f"unresolved_layout={unresolved}")
    print(f"dup_skipped={dup_skipped}")
    if kept_existing:
        print(f"kept_existing={kept_existing}")
    if skipped_integrity:
        print(f"skipped_integrity={skipped_integrity}")
    if skipped_duration:
        print(f"skipped_duration={skipped_duration}")
    print(f"skipped={skipped}")
    print(f"errors={errored}")
    print(f"move_log={args.move_log}")
    print(f"selection_mode={selection_mode}")
    if has_identity_mapping and not args.allow_multiple_per_identity:
        print(f"selection_identities_scanned={selection_stats['identities_scanned']}")
        print(f"selection_candidates={selection_stats['selected']}")
        if args.require_preferred_asset:
            print(f"selection_skipped_no_preferred={selection_stats['skipped_no_preferred']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
