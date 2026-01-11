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


def process(marked_csv: Path, keep_dest: Path | None, drop_dest: Path | None, root: Path, execute: bool) -> None:
    with marked_csv.open() as f:
        reader = csv.DictReader(f)
        keep_actions = 0
        drop_actions = 0
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
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
                    print(f"[KEEP] copied {path} -> {target}")
                else:
                    print(f"[DRY KEEP] would copy {path} -> {target}")
                keep_actions += 1
            elif action == "DROP":
                if drop_dest:
                    target = drop_dest / rel
                    if execute:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(path, target)
                        print(f"[DROP] moved {path} -> {target}")
                    else:
                        print(f"[DRY DROP] would move {path} -> {target}")
                else:
                    if execute:
                        path.unlink(missing_ok=True)
                        print(f"[DROP] deleted {path}")
                    else:
                        print(f"[DRY DROP] would delete {path}")
                drop_actions += 1
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
    args = parser.parse_args()

    process(
        marked_csv=Path(args.marked).expanduser(),
        keep_dest=Path(args.keep_dest).expanduser() if args.keep_dest else None,
        drop_dest=Path(args.drop_dest).expanduser() if args.drop_dest else None,
        root=Path(args.relative_root),
        execute=args.execute,
    )


if __name__ == "__main__":
    main()
