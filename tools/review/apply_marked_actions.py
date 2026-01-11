#!/usr/bin/env python3
"""
Apply KEEP/DROP actions from a marked CSV.

Default is dry-run (no file changes). Use --execute to perform actions.
Actions:
- KEEP: copy to --keep-dest preserving relative path from --relative-root (default "/")
- DROP: if --drop-dest is provided, move there preserving relative path; otherwise report only

CSV columns expected: group_id,path,library,zone,action,reason,confidence,conflict_label,duration_diff,bitrate_diff,sample_rate_diff,bit_depth_diff,integrity_state,flac_ok
"""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path
from typing import Iterable


def rel_to(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.as_posix().lstrip("/"))


def process(
    marked_csv: Path,
    keep_dest: Path | None,
    drop_dest: Path | None,
    root: Path,
    execute: bool,
    skip_missing: bool,
    progress_every: int,
) -> None:
    with marked_csv.open() as f:
        # Count rows upfront for a simple countdown tracker.
        total_rows = sum(1 for _ in f) - 1  # subtract header
        f.seek(0)
        reader = csv.DictReader(f)
        keep_actions = 0
        drop_actions = 0
        try:
            for row in reader:
                path = Path(row["path"])
                action = row.get("action")
                rel = rel_to(path, root)
                if action == "KEEP":
                    if not keep_dest:
                        print(f"[SKIP KEEP] no keep_dest set for {path}")
                        continue
                    target = keep_dest / rel
                    if execute:
                        try:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(path, target)
                            print(f"[KEEP] copied {path} -> {target}")
                        except FileNotFoundError:
                            if skip_missing:
                                print(f"[MISSING KEEP] {path} (skipping)")
                                continue
                            raise
                    else:
                        print(f"[DRY KEEP] would copy {path} -> {target}")
                    keep_actions += 1
                elif action == "DROP":
                    if drop_dest:
                        target = drop_dest / rel
                        if execute:
                            try:
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.move(path, target)
                                print(f"[DROP] moved {path} -> {target}")
                            except FileNotFoundError:
                                if skip_missing:
                                    print(f"[MISSING DROP] {path} (skipping)")
                                    continue
                                raise
                        else:
                            print(f"[DRY DROP] would move {path} -> {target}")
                    else:
                        if execute:
                            try:
                                path.unlink(missing_ok=True)
                                print(f"[DROP] deleted {path}")
                            except FileNotFoundError:
                                if skip_missing:
                                    print(f"[MISSING DROP] {path} (skipping)")
                                    continue
                                raise
                        else:
                            print(f"[DRY DROP] would delete {path}")
                    drop_actions += 1
                total_done = keep_actions + drop_actions
                if progress_every and total_done % progress_every == 0:
                    remaining = max(total_rows - total_done, 0)
                    print(
                        f"[PROGRESS] processed {total_done}/{total_rows} "
                        f"(KEEP {keep_actions}, DROP {drop_actions}, remaining {remaining})"
                    )
        except KeyboardInterrupt:
            print(f"\nInterrupted. Summary so far: KEEP {keep_actions}, DROP {drop_actions} (execute={execute})")
            return
        print(f"Summary: KEEP {keep_actions}, DROP {drop_actions} (execute={execute})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply KEEP/DROP from marked CSV (dry-run by default).")
    parser.add_argument(
        "--marked",
        default="/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_marked_suggestions.csv",
        help="CSV with action column (KEEP/DROP)",
    )
    parser.add_argument(
        "--keep-dest",
        help="Destination root for KEEP files (required if any KEEP rows will be applied)",
    )
    parser.add_argument(
        "--drop-dest",
        help="Optional destination for DROP files (if omitted, DROP will delete)",
    )
    parser.add_argument(
        "--relative-root",
        default="/",
        help="Root to compute relative paths for copying/moving (default '/')",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform actions; otherwise dry-run",
    )
    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip missing source files instead of aborting",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=500,
        help="Print a progress line every N processed rows (0 to disable)",
    )
    args = parser.parse_args()

    process(
        marked_csv=Path(args.marked).expanduser(),
        keep_dest=Path(args.keep_dest).expanduser() if args.keep_dest else None,
        drop_dest=Path(args.drop_dest).expanduser() if args.drop_dest else None,
        root=Path(args.relative_root),
        execute=args.execute,
        skip_missing=args.skip_missing,
        progress_every=max(args.progress_every, 0),
    )


if __name__ == "__main__":
    main()
