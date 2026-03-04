#!/usr/bin/env python3
"""
Consolidate high-quality AIFF files into a destination folder and remove
low-quality (I8) AIFF files from that destination.

Behavior:
- Scans one or more source roots for .aif/.aiff
- Moves only non-I8 files into --dest-root
- Optionally removes I8 files already present in --dest-root
- Dry-run by default; use --execute to apply changes
- Does not touch tagslut DB
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from _progress import ProgressTracker


BIT_DEPTH_RE = re.compile(r"source bit depth:\s*([A-Za-z0-9]+)", re.IGNORECASE)


@dataclass
class MoveRow:
    source_path: str
    source_root: str
    bit_depth: str
    destination_path: str
    action: str
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Move high-quality AIFF to destination and purge destination I8")
    parser.add_argument(
        "--roots",
        nargs="+",
        default=["/Users/georgeskhawam/Music/AIFF", "/Volumes/RKRDBX/Contents/Music"],
        help="Source roots to consolidate from",
    )
    parser.add_argument("--dest-root", default="/Volumes/MUSIC/AIFF", help="Destination root for high-quality AIFF")
    parser.add_argument(
        "--strip-root-label",
        action="store_true",
        help="Do not prefix destination with source root label (default keeps label to avoid collisions)",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite destination files when present")
    parser.add_argument(
        "--purge-dest-low-quality",
        action="store_true",
        help="Remove I8 files found under destination root",
    )
    parser.add_argument("--limit", type=int, help="Optional max files per source root")
    parser.add_argument("--progress-interval", type=int, default=50, help="Progress print interval")
    parser.add_argument("--execute", action="store_true", help="Apply changes (default: dry-run)")
    return parser.parse_args()


def root_label(path: Path) -> str:
    parts = [p for p in path.parts if p not in {"/", ""}]
    return "__".join(parts)


def probe_bit_depth(path: Path) -> str:
    result = subprocess.run(["afinfo", str(path)], capture_output=True, text=True, check=False)
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    match = BIT_DEPTH_RE.search(text)
    if not match:
        return "UNKNOWN"
    return match.group(1).upper()


def iter_aiff_files(root: Path) -> list[Path]:
    return sorted([p for p in root.rglob("*") if p.suffix.lower() in {".aif", ".aiff"}])


def move_high_quality(
    source: Path,
    source_root: Path,
    dest_root: Path,
    with_label: bool,
    execute: bool,
    overwrite: bool,
) -> MoveRow:
    depth = probe_bit_depth(source)
    rel = source.relative_to(source_root)
    if with_label:
        destination = dest_root / root_label(source_root) / rel
    else:
        destination = dest_root / rel

    if depth == "I8":
        return MoveRow(str(source), str(source_root), depth, str(destination), "skip_low_quality", "I8")

    if destination.exists() and not overwrite:
        return MoveRow(str(source), str(source_root), depth, str(destination), "skip_exists", "destination exists")

    if not execute:
        return MoveRow(str(source), str(source_root), depth, str(destination), "plan_move_high_quality", "dry_run")

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and overwrite:
            destination.unlink()
        shutil.move(str(source), str(destination))
        return MoveRow(str(source), str(source_root), depth, str(destination), "moved_high_quality", "ok")
    except Exception as exc:  # noqa: BLE001
        return MoveRow(str(source), str(source_root), depth, str(destination), "error", f"{type(exc).__name__}: {exc}")


def purge_dest_i8(dest_root: Path, execute: bool) -> list[MoveRow]:
    rows: list[MoveRow] = []
    files = iter_aiff_files(dest_root)
    for file_path in files:
        depth = probe_bit_depth(file_path)
        if depth != "I8":
            continue
        if execute:
            try:
                file_path.unlink(missing_ok=True)
                rows.append(
                    MoveRow(
                        str(file_path),
                        str(dest_root),
                        depth,
                        str(file_path),
                        "deleted_dest_low_quality",
                        "ok",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    MoveRow(
                        str(file_path),
                        str(dest_root),
                        depth,
                        str(file_path),
                        "error",
                        f"{type(exc).__name__}: {exc}",
                    )
                )
        else:
            rows.append(
                MoveRow(
                    str(file_path),
                    str(dest_root),
                    depth,
                    str(file_path),
                    "plan_delete_dest_low_quality",
                    "dry_run",
                )
            )
    return rows


def main() -> int:
    args = parse_args()
    source_roots = [Path(r).expanduser().resolve() for r in args.roots]
    dest_root = Path(args.dest_root).expanduser().resolve()
    dest_root.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_csv = Path("artifacts") / f"aiff_consolidate_{ts}.csv"
    log_csv.parent.mkdir(parents=True, exist_ok=True)

    all_rows: list[MoveRow] = []
    for root in source_roots:
        if not root.exists():
            print(f"SKIP missing root: {root}")
            continue
        files = iter_aiff_files(root)
        if args.limit and args.limit > 0:
            files = files[: args.limit]

        print(f"Scanning {len(files)} files in {root}")
        progress = ProgressTracker(total=len(files), interval=int(args.progress_interval), label="Consolidate")
        for idx, file_path in enumerate(files, start=1):
            row = move_high_quality(
                source=file_path,
                source_root=root,
                dest_root=dest_root,
                with_label=not bool(args.strip_root_label),
                execute=bool(args.execute),
                overwrite=bool(args.overwrite),
            )
            all_rows.append(row)
            if idx % max(1, int(args.progress_interval)) == 0 or idx == len(files):
                print(progress.line(idx))

    if args.purge_dest_low_quality:
        print(f"Purging low-quality I8 files in destination: {dest_root}")
        purge_rows = purge_dest_i8(dest_root=dest_root, execute=bool(args.execute))
        all_rows.extend(purge_rows)

    with log_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_path", "source_root", "bit_depth", "destination_path", "action", "detail"],
        )
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row.__dict__)

    moved = sum(1 for r in all_rows if r.action == "moved_high_quality")
    planned = sum(1 for r in all_rows if r.action == "plan_move_high_quality")
    skipped_low = sum(1 for r in all_rows if r.action == "skip_low_quality")
    skipped_exists = sum(1 for r in all_rows if r.action == "skip_exists")
    deleted_low = sum(1 for r in all_rows if r.action == "deleted_dest_low_quality")
    planned_delete = sum(1 for r in all_rows if r.action == "plan_delete_dest_low_quality")
    errors = sum(1 for r in all_rows if r.action == "error")

    print("---")
    print(f"Moved high-quality: {moved}")
    print(f"Planned high-quality moves: {planned}")
    print(f"Skipped low-quality I8 in sources: {skipped_low}")
    print(f"Skipped existing destination files: {skipped_exists}")
    print(f"Deleted low-quality I8 in destination: {deleted_low}")
    print(f"Planned low-quality destination deletions: {planned_delete}")
    print(f"Errors: {errors}")
    print(f"Log CSV: {log_csv}")
    print("DB untouched: yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
