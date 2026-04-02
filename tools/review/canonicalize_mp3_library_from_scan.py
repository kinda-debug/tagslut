#!/usr/bin/env python3
"""
Make MP3_LIBRARY the canonical MP3 library from an mp3 scan CSV.

This script does two things:
1) Plans deduplication inside MP3_LIBRARY by audio hash.
2) Plans importing source-only tracks into MP3_LIBRARY.

Default mode is dry-run planner only. Execution flags are opt-in.
"""

from __future__ import annotations

import argparse
import csv
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Row:
    path: Path
    sha256: str
    size_bytes: int
    bitrate: int


def norm_prefix(prefix: str) -> str:
    p = prefix.strip()
    if not p.endswith("/"):
        p += "/"
    return p


def starts_with(path: Path, prefix: str) -> bool:
    return str(path).startswith(prefix)


def safe_int(value: str) -> int:
    try:
        return int(float((value or "").strip() or "0"))
    except Exception:
        return 0


def preferred_keep(rows: list[Row]) -> Row:
    def score(r: Row) -> tuple[int, int, int, str]:
        # Prefer higher bitrate, larger file, then shorter path deterministically.
        return (r.bitrate, r.size_bytes, -len(str(r.path)), str(r.path))

    return sorted(rows, key=score, reverse=True)[0]


def build_unique_target(base_dir: Path, source: Path) -> Path:
    candidate = base_dir / source.name
    if not candidate.exists():
        return candidate

    stem = source.stem
    suffix = source.suffix
    idx = 2
    while True:
        candidate = base_dir / f"{stem}__{idx}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


def read_scan_rows(scan_csv: Path, mp3_prefix: str, dj_prefix: str) -> tuple[list[Row], list[Row]]:
    mp3_rows: list[Row] = []
    dj_rows: list[Row] = []

    with scan_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            path_raw = (r.get("path") or "").strip()
            if not path_raw.lower().endswith(".mp3"):
                continue

            p = Path(path_raw)
            row = Row(
                path=p,
                sha256=(r.get("sha256") or "").strip(),
                size_bytes=safe_int(r.get("size_bytes") or "0"),
                bitrate=safe_int(r.get("bitrate") or "0"),
            )

            if starts_with(p, mp3_prefix):
                mp3_rows.append(row)
            elif starts_with(p, dj_prefix):
                dj_rows.append(row)

    return mp3_rows, dj_rows


def write_dedupe_plan(path: Path, plan: list[tuple[str, Path, Path]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sha256", "keep_path", "drop_path"])
        for sha, keep, drop in plan:
            w.writerow([sha, str(keep), str(drop)])


def write_dj_import_plan(path: Path, plan: list[tuple[str, Path, Path, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sha256", "source_dj_path", "target_mp3_path", "reason"])
        for sha, src, tgt, reason in plan:
            w.writerow([sha, str(src), str(tgt), reason])


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan/execute MP3_LIBRARY canonicalization from scan CSV")
    parser.add_argument("--scan-csv", type=Path, default=Path("data/mp3_scan_volumes_music.csv"))
    parser.add_argument("--mp3-prefix", default="/Volumes/MUSIC/MP3_LIBRARY/")
    parser.add_argument("--dj-prefix", default="/Volumes/MUSIC/MP3_IMPORT_SOURCE/")
    parser.add_argument("--out-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--import-subdir",
        default="_from_dj_only",
        help="Subdirectory under MP3_LIBRARY where DJ-only imports are copied",
    )
    parser.add_argument("--execute-copy", action="store_true", help="Copy DJ-only planned files into MP3_LIBRARY")
    parser.add_argument(
        "--execute-quarantine-duplicates",
        action="store_true",
        help="Move duplicate MP3_LIBRARY files (drop_path) into --quarantine-dir",
    )
    parser.add_argument(
        "--quarantine-dir",
        type=Path,
        default=Path("/Volumes/MUSIC/_quarantine/mp3_library_duplicates"),
        help="Target directory for duplicate files when --execute-quarantine-duplicates is set",
    )
    args = parser.parse_args()

    scan_csv = args.scan_csv.expanduser().resolve()
    if not scan_csv.exists():
        raise SystemExit(f"Scan CSV not found: {scan_csv}")

    mp3_prefix = norm_prefix(args.mp3_prefix)
    dj_prefix = norm_prefix(args.dj_prefix)
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    mp3_rows, dj_rows = read_scan_rows(scan_csv, mp3_prefix, dj_prefix)

    mp3_by_sha: dict[str, list[Row]] = defaultdict(list)
    dj_by_sha: dict[str, list[Row]] = defaultdict(list)

    for row in mp3_rows:
        if row.sha256:
            mp3_by_sha[row.sha256].append(row)
    for row in dj_rows:
        if row.sha256:
            dj_by_sha[row.sha256].append(row)

    # 1) Dedupe plan inside MP3_LIBRARY.
    dedupe_plan: list[tuple[str, Path, Path]] = []
    for sha, rows in mp3_by_sha.items():
        if len(rows) <= 1:
            continue
        keep = preferred_keep(rows)
        for row in rows:
            if row.path == keep.path:
                continue
            dedupe_plan.append((sha, keep.path, row.path))

    # 2) DJ-only import plan (content hash absent from MP3_LIBRARY).
    import_root = Path(mp3_prefix) / args.import_subdir
    dj_import_plan: list[tuple[str, Path, Path, str]] = []
    for sha, rows in dj_by_sha.items():
        if sha in mp3_by_sha:
            continue
        for row in rows:
            target = build_unique_target(import_root, row.path)
            reason = "sha256 present in source MP3 root but absent from MP3_LIBRARY"
            dj_import_plan.append((sha, row.path, target, reason))

    dedupe_csv = out_dir / "mp3_library_dedupe_plan.csv"
    import_csv = out_dir / "mp3_library_import_from_dj_plan.csv"
    write_dedupe_plan(dedupe_csv, dedupe_plan)
    write_dj_import_plan(import_csv, dj_import_plan)

    copied = 0
    copy_missing = 0
    quarantined = 0
    quarantine_missing = 0

    if args.execute_copy:
        for _, src, tgt, _ in dj_import_plan:
            if not src.exists():
                copy_missing += 1
                continue
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tgt)
            copied += 1

    if args.execute_quarantine_duplicates:
        qdir = args.quarantine_dir.expanduser().resolve()
        qdir.mkdir(parents=True, exist_ok=True)
        for _, _, drop in dedupe_plan:
            if not drop.exists():
                quarantine_missing += 1
                continue
            target = build_unique_target(qdir, drop)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(drop), str(target))
            quarantined += 1

    print(f"scan_csv: {scan_csv}")
    print(f"mp3_rows: {len(mp3_rows)}")
    print(f"dj_rows: {len(dj_rows)}")
    print(f"mp3_unique_sha: {len(mp3_by_sha)}")
    print(f"dj_unique_sha: {len(dj_by_sha)}")
    print(f"dedupe_actions: {len(dedupe_plan)}")
    print(f"import_actions: {len(dj_import_plan)}")
    print(f"dedupe_plan_csv: {dedupe_csv}")
    print(f"import_plan_csv: {import_csv}")

    if args.execute_copy:
        print(f"copied_from_dj: {copied}")
        print(f"copy_missing_source: {copy_missing}")
    else:
        print("copy_mode: dry-run")

    if args.execute_quarantine_duplicates:
        print(f"duplicates_quarantined: {quarantined}")
        print(f"quarantine_missing_source: {quarantine_missing}")
    else:
        print("quarantine_mode: dry-run")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
