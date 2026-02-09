#!/usr/bin/env python3
"""
plan_fpcalc_promote_unique_to_final_library.py

Plan MOVE-only actions to build the FINAL_LIBRARY from one or more *source* roots:

- Promote unique audio (by fpcalc fingerprint) into FINAL_LIBRARY strict naming convention
- Stash healthy duplicates on the SAME source volume under /Volumes/<VOL>/_work/<stash-folder-name>/...
- Quarantine files missing fingerprint (optional bucket) to a quarantine root

Crucially: this planner treats the FINAL_LIBRARY as **read-only**. If a fingerprint
already exists under --final-root, the source copies are stashed and nothing in
the FINAL_LIBRARY is moved.

This script does NOT move files. It writes plan CSV(s) for move_from_plan.py.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.metadata.canon import apply_canon, load_canon_rules
from dedupe.utils.final_library_layout import FinalLibraryLayoutError, build_final_library_destination


@dataclass(frozen=True)
class FileRow:
    path: str
    size: int
    duration: float
    sample_rate: int
    bit_depth: int
    bitrate: int
    fingerprint: str | None
    flac_ok: int | None
    integrity_state: str | None
    metadata_json: str | None


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "ignore")).hexdigest()


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value).strip()


def _safe_load_meta(metadata_json: Optional[str]) -> dict[str, Any]:
    if not metadata_json:
        return {}
    try:
        obj = json.loads(metadata_json)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _meta_score(meta: dict[str, Any]) -> int:
    # Lightweight tag richness heuristic; bigger is better.
    keys = [
        ("artist", "albumartist"),
        ("title",),
        ("album",),
        ("isrc",),
        ("label",),
        ("date", "originaldate", "year"),
        ("genre",),
        ("bpm",),
        ("initialkey", "key"),
        ("musicbrainz_recordingid",),
        ("beatport_track_id",),
    ]
    score = 0
    for variants in keys:
        for k in variants:
            v = meta.get(k)
            if _norm_text(v):
                score += 1
                break
    return score


def _quality_key(row: FileRow) -> tuple[int, int, int, int]:
    return (int(row.sample_rate or 0), int(row.bit_depth or 0), int(row.bitrate or 0), int(row.size or 0))


def _volume_name(path: Path) -> str:
    parts = path.resolve().parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "Volumes":
        return parts[2]
    return ""


def _relative_under_volume(path: Path) -> Path:
    parts = path.resolve().parts
    if len(parts) >= 4 and parts[0] == "/" and parts[1] == "Volumes":
        return Path(*parts[3:])  # after /Volumes/<VOLUME_NAME>/
    return Path(path.name)


def _prefix_where(prefixes: Iterable[Path]) -> tuple[str, list[str]]:
    parts: list[str] = []
    params: list[str] = []
    for p in prefixes:
        s = str(p.expanduser().resolve())
        if not s.endswith("/"):
            s += "/"
        parts.append("path LIKE ?")
        params.append(s + "%")
    if not parts:
        return "1=0", []
    return "(" + " OR ".join(parts) + ")", params


def _prefer_rank(path_str: str, prefer_prefixes: list[str]) -> int:
    for idx, prefix in enumerate(prefer_prefixes):
        if path_str.startswith(prefix):
            return idx
    return 10_000


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Plan promote unique fpcalc audio into FINAL_LIBRARY, stash dupes, quarantine missing fingerprints",
    )
    ap.add_argument("--db", type=Path, default=None, help="SQLite DB path (default: $DEDUPE_DB)")
    ap.add_argument("--source-root", type=Path, action="append", required=True, help="Source root prefix (repeatable)")
    ap.add_argument(
        "--final-root",
        type=Path,
        required=True,
        help="Existing FINAL_LIBRARY root (read-only for this planner)",
    )
    ap.add_argument(
        "--dest-root",
        type=Path,
        required=True,
        help="Destination FINAL_LIBRARY root (where promoted keepers will go)",
    )
    ap.add_argument(
        "--prefer-root",
        type=Path,
        action="append",
        default=[],
        help="Source prefix preference for keeper selection (repeatable; tie-break only)",
    )
    ap.add_argument(
        "--stash-folder-name",
        required=True,
        help="Folder name under each source volume at /Volumes/<VOL>/_work/<name>/...",
    )
    ap.add_argument(
        "--quarantine-root",
        type=Path,
        default=Path("/Volumes/SAD/_work/MUSIC/_work/quarantine/_fpcalc_missing"),
        help="Quarantine root for missing fingerprints (only used with --quarantine-missing-fp)",
    )
    ap.add_argument(
        "--quarantine-missing-fp",
        action="store_true",
        help="Emit MOVE rows for missing-fingerprint files into --quarantine-root (default: do nothing)",
    )
    ap.add_argument("--out-dir", type=Path, default=Path("artifacts/compare"), help="Output directory")
    ap.add_argument("--stamp", default=None, help="Optional timestamp stamp override (default: now UTC)")
    ap.add_argument("--limit-fps", type=int, help="Limit number of fingerprint groups (for testing)")
    ap.add_argument("--canon/--no-canon", dest="canon", default=True, help="Apply canonical tag rules (default: on)")
    ap.add_argument("--canon-rules", type=Path, help="Path to canon rules JSON (default: tools/rules/library_canon.json)")
    ap.add_argument(
        "--strip-brackets/--keep-brackets",
        dest="strip_brackets",
        default=True,
        help="Remove []{} bracket characters from path components (default: strip)",
    )
    return ap.parse_args()


def _default_canon_rules_path() -> Path:
    return Path(__file__).parents[2] / "tools" / "rules" / "library_canon.json"


def main() -> int:
    args = parse_args()
    source_roots = [r.expanduser().resolve() for r in args.source_root]
    final_root = args.final_root.expanduser().resolve()
    dest_root = args.dest_root.expanduser().resolve()
    quarantine_root = args.quarantine_root.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = args.stamp or _now_stamp()

    db_path = (args.db or Path(os.environ.get("DEDUPE_DB", ""))).expanduser().resolve()
    if not str(db_path):
        raise SystemExit("ERROR: --db not provided and $DEDUPE_DB is not set")
    if not db_path.exists():
        raise SystemExit(f"ERROR: DB not found: {db_path}")

    prefer_prefixes: list[str] = []
    for p in args.prefer_root:
        s = str(p.expanduser().resolve())
        if not s.endswith("/"):
            s += "/"
        prefer_prefixes.append(s)

    canon_rules = None
    if args.canon:
        rules_path = args.canon_rules.expanduser().resolve() if args.canon_rules else _default_canon_rules_path()
        canon_rules = load_canon_rules(rules_path)

    out_promote = out_dir / f"plan_promote_fpcalc_unique_final_{stamp}.csv"
    out_stash = out_dir / f"plan_stash_fpcalc_unique_final_{stamp}.csv"
    out_quarantine = out_dir / f"plan_quarantine_fpcalc_unique_final_{stamp}.csv"
    out_summary = out_dir / f"plan_fpcalc_unique_final_summary_{stamp}.json"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        final_prefix = str(final_root)
        if not final_prefix.endswith("/"):
            final_prefix += "/"
        final_fps = {
            str(r[0]).strip()
            for r in conn.execute(
                """
                SELECT DISTINCT fingerprint
                FROM files
                WHERE path LIKE ?
                  AND fingerprint IS NOT NULL
                  AND fingerprint != ''
                """,
                (final_prefix + "%",),
            ).fetchall()
            if r[0]
        }

        where_src, params_src = _prefix_where(source_roots)
        rows = conn.execute(
            f"""
            SELECT
                path,
                size,
                duration,
                sample_rate,
                bit_depth,
                bitrate,
                fingerprint,
                flac_ok,
                integrity_state,
                metadata_json
            FROM files
            WHERE {where_src}
            ORDER BY fingerprint, path
            """,
            params_src,
        ).fetchall()
    finally:
        conn.close()

    files: list[FileRow] = []
    for r in rows:
        files.append(
            FileRow(
                path=r["path"],
                size=int(r["size"] or 0),
                duration=float(r["duration"] or 0.0),
                sample_rate=int(r["sample_rate"] or 0),
                bit_depth=int(r["bit_depth"] or 0),
                bitrate=int(r["bitrate"] or 0),
                fingerprint=(r["fingerprint"] or "").strip() or None,
                flac_ok=r["flac_ok"],
                integrity_state=r["integrity_state"],
                metadata_json=r["metadata_json"],
            )
        )

    if not files:
        print("No DB rows matched source roots.")
        return 0

    missing_fp = [f for f in files if not f.fingerprint]
    with_fp = [f for f in files if f.fingerprint]

    by_fp: dict[str, list[FileRow]] = {}
    for f in with_fp:
        by_fp.setdefault(f.fingerprint or "", []).append(f)

    fps = sorted(by_fp.keys(), key=lambda fp: (_sha1_text(fp), fp))
    if args.limit_fps and args.limit_fps > 0:
        fps = fps[: args.limit_fps]

    promote_rows: list[dict[str, str]] = []
    stash_rows: list[dict[str, str]] = []
    quarantine_rows: list[dict[str, str]] = []

    dest_to_sources: dict[str, list[str]] = {}

    missing_files_skipped = 0
    unhealthy_files_skipped = 0

    bytes_promote = 0
    bytes_stash = 0
    bytes_quarantine = 0

    def is_healthy(fr: FileRow) -> bool:
        if fr.flac_ok is not None and int(fr.flac_ok) != 1:
            return False
        if fr.integrity_state and str(fr.integrity_state).strip().lower() != "valid":
            return False
        return True

    for group_idx, fp in enumerate(fps, start=1):
        members = by_fp[fp]

        # Remove missing paths
        existing: list[FileRow] = []
        for m in members:
            if Path(m.path).exists():
                existing.append(m)
            else:
                missing_files_skipped += 1

        if not existing:
            continue

        healthy = [m for m in existing if is_healthy(m)]
        if not healthy:
            unhealthy_files_skipped += len(existing)
            continue

        fp_sha1 = _sha1_text(fp)

        if fp in final_fps:
            # Audio already present in FINAL_LIBRARY -> stash all healthy source copies.
            for m in healthy:
                src_path = Path(m.path)
                vol = _volume_name(src_path)
                if not vol:
                    continue
                stash_root = Path("/Volumes") / vol / "_work" / args.stash_folder_name
                dest_path = stash_root / _relative_under_volume(src_path)
                if dest_path.exists():
                    continue
                meta = _safe_load_meta(m.metadata_json)
                stash_rows.append(
                    {
                        "action": "MOVE",
                        "group": str(group_idx),
                        "fp_sha1": fp_sha1,
                        "isrc": _norm_text(meta.get("isrc")),
                        "artist": _norm_text(meta.get("artist") or meta.get("albumartist")),
                        "title": _norm_text(meta.get("title")),
                        "path": m.path,
                        "dest_path": str(dest_path),
                        "reason": "stash_fpcalc_in_final",
                    }
                )
                bytes_stash += int(m.size or 0)
            continue

        # Keeper selection within the source group:
        # quality -> metadata richness -> prefer-root rank -> path
        def keeper_sort_key(m: FileRow) -> tuple[tuple[int, int, int, int], int, int, str]:
            meta = _safe_load_meta(m.metadata_json)
            meta_score = _meta_score(meta)
            prefer_rank = _prefer_rank(m.path, prefer_prefixes) if prefer_prefixes else 10_000
            return (_quality_key(m), meta_score, -prefer_rank, m.path)

        keeper = sorted(healthy, key=keeper_sort_key, reverse=True)[0]
        keeper_meta = _safe_load_meta(keeper.metadata_json)

        tags_for_layout: Mapping[str, Any]
        if canon_rules:
            try:
                tags_for_layout = apply_canon(dict(keeper_meta), canon_rules)
            except Exception as e:
                promote_rows.append(
                    {
                        "action": "SKIP",
                        "group": str(group_idx),
                        "fp_sha1": fp_sha1,
                        "isrc": _norm_text(keeper_meta.get("isrc")),
                        "artist": _norm_text(keeper_meta.get("artist") or keeper_meta.get("albumartist")),
                        "title": _norm_text(keeper_meta.get("title")),
                        "path": keeper.path,
                        "dest_path": "",
                        "reason": f"canon_error:{type(e).__name__}",
                    }
                )
                continue
        else:
            tags_for_layout = keeper_meta

        try:
            layout = build_final_library_destination(
                tags_for_layout,
                dest_root,
                strip_brackets=bool(args.strip_brackets),
            )
            dest = layout.dest_path
        except FinalLibraryLayoutError as e:
            msg = str(e)
            if msg.startswith("missing") or "missing required tag" in msg:
                reason = f"missing_tags:{msg}"
            elif msg.startswith("path component too long"):
                reason = f"path_too_long:{msg}"
            else:
                reason = f"layout_rejected:{msg}"
            promote_rows.append(
                {
                    "action": "SKIP",
                    "group": str(group_idx),
                    "fp_sha1": fp_sha1,
                    "isrc": _norm_text(keeper_meta.get("isrc")),
                    "artist": _norm_text(keeper_meta.get("artist") or keeper_meta.get("albumartist")),
                    "title": _norm_text(keeper_meta.get("title")),
                    "path": keeper.path,
                    "dest_path": "",
                    "reason": reason,
                }
            )
            continue
        except Exception as e:
            promote_rows.append(
                {
                    "action": "SKIP",
                    "group": str(group_idx),
                    "fp_sha1": fp_sha1,
                    "isrc": _norm_text(keeper_meta.get("isrc")),
                    "artist": _norm_text(keeper_meta.get("artist") or keeper_meta.get("albumartist")),
                    "title": _norm_text(keeper_meta.get("title")),
                    "path": keeper.path,
                    "dest_path": "",
                    "reason": f"layout_error:{type(e).__name__}",
                }
            )
            continue

        dest_s = str(dest)
        if dest.exists():
            promote_rows.append(
                {
                    "action": "SKIP",
                    "group": str(group_idx),
                    "fp_sha1": fp_sha1,
                    "isrc": _norm_text(keeper_meta.get("isrc")),
                    "artist": _norm_text(keeper_meta.get("artist") or keeper_meta.get("albumartist")),
                    "title": _norm_text(keeper_meta.get("title")),
                    "path": keeper.path,
                    "dest_path": dest_s,
                    "reason": "dest_exists",
                }
            )
        else:
            promote_rows.append(
                {
                    "action": "MOVE",
                    "group": str(group_idx),
                    "fp_sha1": fp_sha1,
                    "isrc": _norm_text(keeper_meta.get("isrc")),
                    "artist": _norm_text(keeper_meta.get("artist") or keeper_meta.get("albumartist")),
                    "title": _norm_text(keeper_meta.get("title")),
                    "path": keeper.path,
                    "dest_path": dest_s,
                    "reason": "final_library",
                }
            )
            dest_to_sources.setdefault(dest_s, []).append(keeper.path)
            bytes_promote += int(keeper.size or 0)

        # Stash remaining healthy dupes within the source group.
        for m in healthy:
            if m.path == keeper.path:
                continue
            src_path = Path(m.path)
            vol = _volume_name(src_path)
            if not vol:
                continue
            stash_root = Path("/Volumes") / vol / "_work" / args.stash_folder_name
            dest_path = stash_root / _relative_under_volume(src_path)
            if dest_path.exists():
                continue
            meta = _safe_load_meta(m.metadata_json)
            stash_rows.append(
                {
                    "action": "MOVE",
                    "group": str(group_idx),
                    "fp_sha1": fp_sha1,
                    "isrc": _norm_text(meta.get("isrc")),
                    "artist": _norm_text(meta.get("artist") or meta.get("albumartist")),
                    "title": _norm_text(meta.get("title")),
                    "path": m.path,
                    "dest_path": str(dest_path),
                    "reason": "stash_healthy_dupe_fpcalc",
                }
            )
            bytes_stash += int(m.size or 0)

    # Quarantine missing fingerprints
    if args.quarantine_missing_fp:
        for idx, m in enumerate(missing_fp, start=1):
            src_path = Path(m.path)
            if not src_path.exists():
                missing_files_skipped += 1
                continue
            dest_path = quarantine_root / _relative_under_volume(src_path)
            if dest_path.exists():
                continue
            meta = _safe_load_meta(m.metadata_json)
            quarantine_rows.append(
                {
                    "action": "MOVE",
                    "group": f"missing_fp_{idx}",
                    "fp_sha1": "",
                    "isrc": _norm_text(meta.get("isrc")),
                    "artist": _norm_text(meta.get("artist") or meta.get("albumartist")),
                    "title": _norm_text(meta.get("title")),
                    "path": m.path,
                    "dest_path": str(dest_path),
                    "reason": "quarantine_fpcalc_missing",
                }
            )
            bytes_quarantine += int(m.size or 0)

    # Deconflict: if multiple sources map to the same destination, mark them all SKIP.
    conflict_dests = {d for d, srcs in dest_to_sources.items() if len(srcs) > 1}
    if conflict_dests:
        updated: list[dict[str, str]] = []
        for r in promote_rows:
            if (r.get("action") or "").strip().upper() == "MOVE" and (r.get("dest_path") or "") in conflict_dests:
                r2 = dict(r)
                r2["action"] = "SKIP"
                r2["reason"] = "conflict_same_dest"
                updated.append(r2)
            else:
                updated.append(r)
        promote_rows = updated

    promote_fields = ["action", "group", "fp_sha1", "isrc", "artist", "title", "path", "dest_path", "reason"]
    stash_fields = ["action", "group", "fp_sha1", "isrc", "artist", "title", "path", "dest_path", "reason"]
    quarantine_fields = ["action", "group", "fp_sha1", "isrc", "artist", "title", "path", "dest_path", "reason"]

    for out_path, out_rows, fieldnames in (
        (out_promote, promote_rows, promote_fields),
        (out_stash, stash_rows, stash_fields),
        (out_quarantine, quarantine_rows, quarantine_fields),
    ):
        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(out_rows)

    promote_move = sum(1 for r in promote_rows if (r.get("action") or "").strip().upper() == "MOVE")
    promote_skip = sum(1 for r in promote_rows if (r.get("action") or "").strip().upper() != "MOVE")

    summary = {
        "stamp": stamp,
        "db": str(db_path),
        "source_roots": [str(r) for r in source_roots],
        "final_root": str(final_root),
        "dest_root": str(dest_root),
        "stash_folder_name": args.stash_folder_name,
        "quarantine_root": str(quarantine_root),
        "scoped_files_total": len(files),
        "scoped_files_with_fp": len(with_fp),
        "scoped_files_missing_fp": len(missing_fp),
        "final_fingerprints_distinct": len(final_fps),
        "planned": {
            "promote_move": promote_move,
            "promote_skip": promote_skip,
            "stash_move": len(stash_rows),
            "quarantine_move": len(quarantine_rows),
            "conflict_dest_count": len(conflict_dests),
        },
        "skipped": {
            "missing_files": missing_files_skipped,
            "unhealthy_files": unhealthy_files_skipped,
        },
        "bytes": {
            "promote": bytes_promote,
            "stash": bytes_stash,
            "quarantine": bytes_quarantine,
        },
        "outputs": {
            "promote_plan_csv": str(out_promote),
            "stash_plan_csv": str(out_stash),
            "quarantine_plan_csv": str(out_quarantine),
            "summary_json": str(out_summary),
        },
    }
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Scoped source rows: {len(files)} (with_fp={len(with_fp)} missing_fp={len(missing_fp)})")
    print(f"FINAL_LIBRARY distinct fingerprints: {len(final_fps)}")
    print(f"Planned promote: MOVE={promote_move} SKIP={promote_skip}")
    print(f"Planned stash MOVE rows: {len(stash_rows)}")
    print(f"Planned quarantine MOVE rows: {len(quarantine_rows)}")
    if conflict_dests:
        print(f"Conflicts (same dest): {len(conflict_dests)} destinations")
    print(f"Wrote: {out_promote}")
    print(f"Wrote: {out_stash}")
    print(f"Wrote: {out_quarantine}")
    print(f"Wrote: {out_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
