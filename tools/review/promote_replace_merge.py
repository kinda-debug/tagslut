#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Promote tracks with collision replace + metadata merge")
    ap.add_argument("source", type=Path)
    ap.add_argument("--dest", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    _repo = Path(__file__).resolve().parents[2]
    ap.add_argument("--canon-rules", type=Path, default=_repo / "tools/rules/library_canon.json")
    ap.add_argument("--move-log", type=Path, default=_repo / "artifacts/logs/file_move_mdl_replace.jsonl")
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

    try:
        for i, src in enumerate(files, 1):
            try:
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
                    continue

                moved += 1
                if args.execute:
                    db_updated += db_update_path(conn, src, dest)

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
