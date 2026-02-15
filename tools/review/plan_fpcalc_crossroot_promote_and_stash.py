#!/usr/bin/env python3
"""
plan_fpcalc_crossroot_promote_and_stash.py

Generate MOVE-only plans for fpcalc-identical audio dupes spanning multiple roots:
- Promote exactly ONE keeper per dupe-group to a SAD staging folder
- Stash all remaining healthy dupes on the SAME source volume in a special folder

Inputs:
- tagslut DB (files table) with `fingerprint` already populated (e.g. via audio_dupe_audit.py --execute)
- one or more --root prefixes (repeatable; require >=2)

Outputs:
- artifacts/compare/plan_promote_fpcalc_crossroot_<ts>.csv
- artifacts/compare/plan_stash_fpcalc_crossroot_<ts>.csv
- artifacts/compare/plan_fpcalc_crossroot_summary_<ts>.json

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
    fingerprint: str
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
    # Lightweight "tag richness" heuristic; bigger is better.
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


def _root_labels(roots: list[Path]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for r in roots:
        s = str(r.expanduser().resolve())
        if not s.endswith("/"):
            s += "/"
        out.append((r.name or s.rstrip("/").split("/")[-1], s))
    return out


def _match_root_label(path_str: str, labeled_roots: list[tuple[str, str]]) -> str:
    for label, prefix in labeled_roots:
        if path_str.startswith(prefix):
            return label
    return ""


def _prefer_rank(path_str: str, prefer_prefixes: list[str]) -> int:
    for idx, prefix in enumerate(prefer_prefixes):
        if path_str.startswith(prefix):
            return idx
    return 10_000


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Plan promote+stash for fpcalc-identical dupes spanning roots")
    ap.add_argument("--db", type=Path, default=None, help="SQLite DB path (default: $TAGSLUT_DB)")
    ap.add_argument("--root", type=Path, action="append", required=True, help="Root prefix filter (repeatable; >=2)")
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
        default=Path("/Volumes/SAD/_work/MUSIC/_work/staging/_promoted_fpcalc_crossroot"),
        help="Destination root on SAD for promoted keepers",
    )
    ap.add_argument(
        "--stash-folder-name",
        default="_healthy_dupes_fpcalc_crossroot",
        help="Folder name under each source volume (at /Volumes/<VOL>/_work/<name>/...)",
    )
    ap.add_argument("--out-dir", type=Path, default=Path("artifacts/compare"), help="Output directory")
    ap.add_argument("--limit-groups", type=int, help="Limit number of groups (for testing)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    roots = [r.expanduser().resolve() for r in args.root]
    if len(roots) < 2:
        raise SystemExit("ERROR: provide at least 2 --root values")

    db_path = (args.db or Path(os.environ.get("TAGSLUT_DB", ""))).expanduser().resolve()
    if not str(db_path):
        raise SystemExit("ERROR: --db not provided and $TAGSLUT_DB is not set")
    if not db_path.exists():
        raise SystemExit(f"ERROR: DB not found: {db_path}")

    dest_sad_root = args.dest_sad_root.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()

    out_promote = out_dir / f"plan_promote_fpcalc_crossroot_{stamp}.csv"
    out_stash = out_dir / f"plan_stash_healthy_dupes_fpcalc_crossroot_{stamp}.csv"
    out_summary = out_dir / f"plan_fpcalc_crossroot_summary_{stamp}.json"

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
              AND fingerprint IS NOT NULL AND fingerprint != ''
            ORDER BY fingerprint, path
            """,
            params,
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("No rows found with fingerprint under provided roots.")
        return 0

    labeled_roots = _root_labels(roots)

    # Group by fingerprint
    by_fp: dict[str, list[FileRow]] = {}
    for r in rows:
        fp = (r["fingerprint"] or "").strip()
        if not fp:
            continue
        by_fp.setdefault(fp, []).append(
            FileRow(
                path=r["path"],
                size=int(r["size"] or 0),
                duration=float(r["duration"] or 0.0),
                sample_rate=int(r["sample_rate"] or 0),
                bit_depth=int(r["bit_depth"] or 0),
                bitrate=int(r["bitrate"] or 0),
                fingerprint=fp,
                flac_ok=r["flac_ok"],
                integrity_state=r["integrity_state"],
                metadata_json=r["metadata_json"],
            )
        )

    # Filter to duplicate groups that span ALL provided roots.
    dupe_groups: list[tuple[str, list[FileRow]]] = []
    for fp, members in by_fp.items():
        if len(members) < 2:
            continue
        roots_present = {(_match_root_label(m.path, labeled_roots) or m.path) for m in members}
        # Determine which of the declared roots are represented.
        declared_present = {_match_root_label(m.path, labeled_roots) for m in members}
        declared_present.discard("")
        if len(declared_present) < len(labeled_roots):
            continue
        dupe_groups.append((fp, members))

    dupe_groups.sort(key=lambda t: (-len(t[1]), _sha1_text(t[0])))
    if args.limit_groups and args.limit_groups > 0:
        dupe_groups = dupe_groups[: args.limit_groups]

    promote_rows: list[dict[str, str]] = []
    stash_rows: list[dict[str, str]] = []

    missing_files = 0
    skipped_unhealthy = 0

    for group_idx, (fp, members) in enumerate(dupe_groups, start=1):
        fp_sha1 = _sha1_text(fp)

        # Drop missing files (avoid invalid plans)
        members_existing: list[FileRow] = []
        for m in members:
            if Path(m.path).exists():
                members_existing.append(m)
            else:
                missing_files += 1

        if len(members_existing) < 2:
            continue

        # Health gate: require flac_ok=1 and integrity_state=valid when present.
        healthy: list[FileRow] = []
        for m in members_existing:
            if m.flac_ok is not None and int(m.flac_ok) != 1:
                skipped_unhealthy += 1
                continue
            if m.integrity_state and str(m.integrity_state).strip().lower() != "valid":
                skipped_unhealthy += 1
                continue
            healthy.append(m)

        if len(healthy) < 2:
            continue

        # Select keeper: quality -> metadata richness -> prefer_root rank -> path
        def keeper_sort_key(m: FileRow) -> tuple[tuple[int, int, int, int], int, int, str]:
            meta = _safe_load_meta(m.metadata_json)
            meta_score = _meta_score(meta)
            prefer_rank = _prefer_rank(m.path, prefer_prefixes) if prefer_prefixes else 10_000
            return (_quality_key(m), meta_score, -prefer_rank, m.path)

        keeper = sorted(healthy, key=keeper_sort_key, reverse=True)[0]

        # Build MOVE rows
        keeper_path = Path(keeper.path)
        keeper_dest = dest_sad_root / _relative_under_volume(keeper_path)

        keeper_meta = _safe_load_meta(keeper.metadata_json)
        keeper_artist = _norm_text(keeper_meta.get("artist") or keeper_meta.get("albumartist"))
        keeper_title = _norm_text(keeper_meta.get("title"))
        keeper_isrc = _norm_text(keeper_meta.get("isrc"))

        promote_rows.append(
            {
                "action": "MOVE",
                "group": str(group_idx),
                "fp_sha1": fp_sha1,
                "isrc": keeper_isrc,
                "artist": keeper_artist,
                "title": keeper_title,
                "path": keeper.path,
                "dest_path": str(keeper_dest),
                "reason": "promote_fpcalc_crossroot keeper=1",
            }
        )

        for m in healthy:
            if m.path == keeper.path:
                continue
            src_path = Path(m.path)
            vol = _volume_name(src_path)
            if not vol:
                continue
            stash_root = Path("/Volumes") / vol / "_work" / args.stash_folder_name
            dest_path = stash_root / _relative_under_volume(src_path)

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
                    "reason": "stash_healthy_dupe_fpcalc_crossroot keeper=0",
                }
            )

    fieldnames = ["action", "group", "fp_sha1", "isrc", "artist", "title", "path", "dest_path", "reason"]
    with out_promote.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(promote_rows)

    with out_stash.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(stash_rows)

    summary = {
        "db": str(db_path),
        "roots": [str(r) for r in roots],
        "prefer_roots": [str(p) for p in (args.prefer_root or [])],
        "dest_sad_root": str(dest_sad_root),
        "stash_folder_name": args.stash_folder_name,
        "dupe_groups_spanning_all_roots": len(dupe_groups),
        "promote_moves": len(promote_rows),
        "stash_moves": len(stash_rows),
        "missing_files_skipped": missing_files,
        "unhealthy_files_skipped": skipped_unhealthy,
        "outputs": {
            "promote_plan_csv": str(out_promote),
            "stash_plan_csv": str(out_stash),
        },
    }
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Groups planned: {len(dupe_groups)}")
    print(f"Promote MOVE rows: {len(promote_rows)}")
    print(f"Stash MOVE rows: {len(stash_rows)}")
    print(f"Wrote: {out_promote}")
    print(f"Wrote: {out_stash}")
    print(f"Wrote: {out_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

