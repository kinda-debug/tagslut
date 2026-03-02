#!/usr/bin/env python3
"""
Find severely reduced AIFF files (I8), log details, and optionally move them
to a quarantine folder.

Defaults are conservative:
- Dry-run by default (no moves).
- Writes logs to artifacts/.
- Never touches tagslut DB.
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
class Row:
    source_path: str
    source_root: str
    bit_depth: str
    destination_path: str
    action: str
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quarantine low-quality AIFF (I8) files")
    parser.add_argument(
        "--roots",
        nargs="+",
        default=["/Users/georgeskhawam/Music/AIFF", "/Volumes/RKRDBX/Contents/Music"],
        help="One or more roots to scan for AIFF files",
    )
    parser.add_argument(
        "--quarantine-root",
        default="/Volumes/MUSIC/AIFF/_SEVERELY_REDUCED_QUALITY_I8",
        help="Destination root for quarantined files",
    )
    parser.add_argument("--limit", type=int, help="Optional max files to scan per root")
    parser.add_argument("--progress-interval", type=int, default=50, help="Progress print interval")
    parser.add_argument("--execute", action="store_true", help="Move files (default: dry-run)")
    return parser.parse_args()


def root_label(path: Path) -> str:
    parts = [p for p in path.parts if p not in {"/", ""}]
    return "__".join(parts)


def probe_bit_depth(path: Path) -> str:
    result = subprocess.run(["afinfo", str(path)], capture_output=True, text=True, check=False)
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    match = BIT_DEPTH_RE.search(text)
    if not match:
        return "unknown"
    return match.group(1).upper()


def iter_aiff_files(root: Path) -> list[Path]:
    files = sorted([p for p in root.rglob("*") if p.suffix.lower() in {".aif", ".aiff"}])
    return files


def main() -> int:
    args = parse_args()
    roots = [Path(r).expanduser().resolve() for r in args.roots]
    quarantine_root = Path(args.quarantine_root).expanduser().resolve()
    quarantine_root.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_csv = Path("artifacts") / f"aiff_i8_quarantine_{ts}.csv"
    list_txt = Path("artifacts") / f"aiff_i8_quarantine_{ts}.txt"
    unknown_txt = Path("artifacts") / f"aiff_unknown_bitdepth_{ts}.txt"
    log_csv.parent.mkdir(parents=True, exist_ok=True)

    all_rows: list[Row] = []
    i8_paths: list[str] = []
    unknown_paths: list[str] = []

    for root in roots:
        if not root.exists():
            print(f"SKIP root missing: {root}")
            continue
        files = iter_aiff_files(root)
        if args.limit and args.limit > 0:
            files = files[: args.limit]

        label = root_label(root)
        print(f"Scanning {len(files)} files under {root}")
        progress = ProgressTracker(total=len(files), interval=int(args.progress_interval), label="Quarantine")

        for index, source in enumerate(files, start=1):
            depth = probe_bit_depth(source)
            rel = source.relative_to(root)
            dest = quarantine_root / label / rel

            if depth == "I8":
                if args.execute:
                    try:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        if dest.exists():
                            all_rows.append(
                                Row(
                                    str(source),
                                    str(root),
                                    depth,
                                    str(dest),
                                    "skip",
                                    "destination exists",
                                )
                            )
                        else:
                            shutil.move(str(source), str(dest))
                            all_rows.append(Row(str(source), str(root), depth, str(dest), "moved", "ok"))
                            i8_paths.append(str(dest))
                    except Exception as exc:  # noqa: BLE001
                        all_rows.append(
                            Row(
                                str(source),
                                str(root),
                                depth,
                                str(dest),
                                "error",
                                f"{type(exc).__name__}: {exc}",
                            )
                        )
                else:
                    all_rows.append(Row(str(source), str(root), depth, str(dest), "plan_move", "dry_run"))
                    i8_paths.append(str(source))
            elif depth == "UNKNOWN":
                unknown_paths.append(str(source))
                all_rows.append(Row(str(source), str(root), depth, str(dest), "keep", "unknown bit depth"))
            else:
                all_rows.append(Row(str(source), str(root), depth, str(dest), "keep", "not I8"))

            if index % max(1, int(args.progress_interval)) == 0 or index == len(files):
                print(progress.line(index))

    with log_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_path", "source_root", "bit_depth", "destination_path", "action", "detail"],
        )
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row.__dict__)

    list_txt.write_text("\n".join(i8_paths) + ("\n" if i8_paths else ""), encoding="utf-8")
    unknown_txt.write_text("\n".join(unknown_paths) + ("\n" if unknown_paths else ""), encoding="utf-8")

    total = len(all_rows)
    planned = sum(1 for r in all_rows if r.action == "plan_move")
    moved = sum(1 for r in all_rows if r.action == "moved")
    kept = sum(1 for r in all_rows if r.action == "keep")
    skipped = sum(1 for r in all_rows if r.action == "skip")
    errors = sum(1 for r in all_rows if r.action == "error")

    print("---")
    print(f"Total scanned: {total}")
    if args.execute:
        print(f"Moved I8 files: {moved}")
        print(f"Skipped (dest exists): {skipped}")
    else:
        print(f"Planned I8 moves: {planned}")
    print(f"Kept files: {kept}")
    print(f"Errors: {errors}")
    print(f"CSV log: {log_csv}")
    print(f"I8 list: {list_txt}")
    print(f"Unknown bit-depth list: {unknown_txt}")
    print("DB untouched: yes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
