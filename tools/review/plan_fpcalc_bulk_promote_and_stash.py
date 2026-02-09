#!/usr/bin/env python3
"""
plan_fpcalc_bulk_promote_and_stash.py

Bulk MOVE-only plan generator to clear one or more roots:
- Promote ONE keeper per unique fpcalc fingerprint to SAD
- Stash all remaining (healthy) dupes on the SAME source volume
- Quarantine any files missing fingerprint (or unhealthy) to SAD quarantine

This script does NOT move files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


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
    # Tag richness heuristic; bigger is better.
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
    ap = argparse.ArgumentParser(description="Bulk plan to promote unique fpcalc audio and stash dupes")
    ap.add_argument("--db", type=Path, default=None, help="SQLite DB path (default: $DEDUPE_DB)")
    ap.add_argument("--root", type=Path, action="append", required=True, help="Root prefix filter (repeatable)")
    ap.add_argument(
        "--prefer-root",
        type=Path,
        action="append",
        default=[],
        help="Root prefix preference for KEEP (repeatable, first wins; tie-break only)",
    )
    ap.add_argument(
        "--dest-sad-root",
        type=Path,
        required=True,
        help="Destination root on SAD for promoted keepers",
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
        help="Quarantine root (default: SAD quarantine/_fpcalc_missing)",
    )
    ap.add_argument("--out-dir", type=Path, default=Path("artifacts/compare"), help="Output directory")
    ap.add_argument("--limit-fps", type=int, help="Limit number of fingerprint groups (for testing)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    roots = [r.expanduser().resolve() for r in args.root]

    db_path = (args.db or Path(os.environ.get("DEDUPE_DB", ""))).expanduser().resolve()
    if not str(db_path):
        raise SystemExit("ERROR: --db not provided and $DEDUPE_DB is not set")
    if not db_path.exists():
        raise SystemExit(f"ERROR: DB not found: {db_path}")

    dest_sad_root = args.dest_sad_root.expanduser().resolve()
    quarantine_root = args.quarantine_root.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()

    out_promote = out_dir / f"plan_promote_fpcalc_bulk_{stamp}.csv"
    out_stash = out_dir / f"plan_stash_healthy_dupes_fpcalc_bulk_{stamp}.csv"
    out_quarantine = out_dir / f"plan_quarantine_fpcalc_bulk_{stamp}.csv"
    out_summary = out_dir / f"plan_fpcalc_bulk_summary_{stamp}.json"

    prefer_prefixes: list[str] = []
    for p in args.prefer_root:
        s = str(p.expanduser().resolve())
        if not s.endswith("/"):
            s += "/"
        prefer_prefixes.append(s)

    where, params = _prefix_where(roots)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
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
            WHERE {where}
            ORDER BY fingerprint, path
            """,
            params,
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
        print("No DB rows matched roots.")
        return 0

    # Partition missing fingerprint
    missing_fp = [f for f in files if not f.fingerprint]
    with_fp = [f for f in files if f.fingerprint]

    # Group by fingerprint
    by_fp: dict[str, list[FileRow]] = {}
    for f in with_fp:
        by_fp.setdefault(f.fingerprint or "", []).append(f)

    fps = sorted(by_fp.keys(), key=lambda fp: (_sha1_text(fp), fp))
    if args.limit_fps and args.limit_fps > 0:
        fps = fps[: args.limit_fps]

    promote_rows: list[dict[str, str]] = []
    stash_rows: list[dict[str, str]] = []
    quarantine_rows: list[dict[str, str]] = []

    unhealthy_skipped = 0
    missing_files_skipped = 0

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
            unhealthy_skipped += len(existing)
            continue

        # Keeper selection: quality -> metadata richness -> prefer-root rank -> path
        def keeper_sort_key(m: FileRow) -> tuple[tuple[int, int, int, int], int, int, str]:
            meta = _safe_load_meta(m.metadata_json)
            meta_score = _meta_score(meta)
            prefer_rank = _prefer_rank(m.path, prefer_prefixes) if prefer_prefixes else 10_000
            return (_quality_key(m), meta_score, -prefer_rank, m.path)

        keeper = sorted(healthy, key=keeper_sort_key, reverse=True)[0]
        keeper_path = Path(keeper.path)
        keeper_dest = dest_sad_root / _relative_under_volume(keeper_path)

        meta = _safe_load_meta(keeper.metadata_json)
        promote_rows.append(
            {
                "action": "MOVE",
                "group": str(group_idx),
                "fp_sha1": _sha1_text(fp),
                "count": str(len(members)),
                "isrc": _norm_text(meta.get("isrc")),
                "artist": _norm_text(meta.get("artist") or meta.get("albumartist")),
                "title": _norm_text(meta.get("title")),
                "path": keeper.path,
                "dest_path": str(keeper_dest),
                "reason": "promote_fpcalc_bulk keeper=1",
            }
        )
        bytes_promote += int(keeper.size or 0)

        for m in healthy:
            if m.path == keeper.path:
                continue
            src_path = Path(m.path)
            vol = _volume_name(src_path)
            if not vol:
                continue
            stash_root = Path("/Volumes") / vol / "_work" / args.stash_folder_name
            dest_path = stash_root / _relative_under_volume(src_path)
            meta2 = _safe_load_meta(m.metadata_json)
            stash_rows.append(
                {
                    "action": "MOVE",
                    "group": str(group_idx),
                    "fp_sha1": _sha1_text(fp),
                    "count": str(len(members)),
                    "isrc": _norm_text(meta2.get("isrc")),
                    "artist": _norm_text(meta2.get("artist") or meta2.get("albumartist")),
                    "title": _norm_text(meta2.get("title")),
                    "path": m.path,
                    "dest_path": str(dest_path),
                    "reason": "stash_healthy_dupe_fpcalc_bulk keeper=0",
                }
            )
            bytes_stash += int(m.size or 0)

    # Quarantine missing fingerprints (or missing/unhealthy if desired later)
    for idx, m in enumerate(missing_fp, start=1):
        src_path = Path(m.path)
        if not src_path.exists():
            missing_files_skipped += 1
            continue
        dest_path = quarantine_root / _relative_under_volume(src_path)
        meta = _safe_load_meta(m.metadata_json)
        quarantine_rows.append(
            {
                "action": "MOVE",
                "group": f"missing_fp_{idx}",
                "fp_sha1": "",
                "count": "1",
                "isrc": _norm_text(meta.get("isrc")),
                "artist": _norm_text(meta.get("artist") or meta.get("albumartist")),
                "title": _norm_text(meta.get("title")),
                "path": m.path,
                "dest_path": str(dest_path),
                "reason": "quarantine_fpcalc_missing",
            }
        )
        bytes_quarantine += int(m.size or 0)

    fieldnames = [
        "action",
        "group",
        "fp_sha1",
        "count",
        "isrc",
        "artist",
        "title",
        "path",
        "dest_path",
        "reason",
    ]
    for out_path, rows_out in (
        (out_promote, promote_rows),
        (out_stash, stash_rows),
        (out_quarantine, quarantine_rows),
    ):
        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows_out)

    summary = {
        "db": str(db_path),
        "roots": [str(r) for r in roots],
        "prefer_roots": [str(p) for p in (args.prefer_root or [])],
        "dest_sad_root": str(dest_sad_root),
        "stash_folder_name": args.stash_folder_name,
        "quarantine_root": str(quarantine_root),
        "scoped_files_total": len(files),
        "scoped_files_with_fp": len(with_fp),
        "scoped_files_missing_fp": len(missing_fp),
        "fingerprints_distinct": len(fps),
        "promote_moves": len(promote_rows),
        "stash_moves": len(stash_rows),
        "quarantine_moves": len(quarantine_rows),
        "missing_files_skipped": missing_files_skipped,
        "unhealthy_files_skipped": unhealthy_skipped,
        "bytes": {
            "promote": bytes_promote,
            "stash": bytes_stash,
            "quarantine": bytes_quarantine,
        },
        "outputs": {
            "promote_plan_csv": str(out_promote),
            "stash_plan_csv": str(out_stash),
            "quarantine_plan_csv": str(out_quarantine),
        },
    }
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Scoped files: {len(files)} (with_fp={len(with_fp)} missing_fp={len(missing_fp)})")
    print(f"Distinct fingerprints: {len(fps)}")
    print(f"Promote MOVE rows: {len(promote_rows)}")
    print(f"Stash MOVE rows: {len(stash_rows)}")
    print(f"Quarantine MOVE rows: {len(quarantine_rows)}")
    print(f"Wrote: {out_promote}")
    print(f"Wrote: {out_stash}")
    print(f"Wrote: {out_quarantine}")
    print(f"Wrote: {out_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

