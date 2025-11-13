#!/usr/bin/env python3
"""Execute library move plan: move files to NEW_LIBRARY."""

import argparse
import csv
import shutil
from pathlib import Path
from typing import List, Dict


def move_files(plan: List[Dict], commit: bool = False) -> None:
    """Move files according to plan."""
    moved = 0
    failed = 0
    skipped = 0

    for i, item in enumerate(plan, 1):
        source = Path(item['source'])
        dest = Path(item['destination'])

        # Skip if source doesn't exist
        if not source.exists():
            skipped += 1
            print(f"[SKIP] {source.name} (not found)")
            continue

        # Create destination directory
        dest.parent.mkdir(parents=True, exist_ok=True)

        if commit:
            try:
                # Move file
                shutil.move(str(source), str(dest))
                moved += 1
                if i % 100 == 0:
                    print(f"[{i:5}] Moved {source.name}")
            except Exception as e:
                failed += 1
                print(f"[ERROR] {source.name}: {e}")
        else:
            # Dry-run: just show what would happen
            if i <= 5:  # Show first 5
                print(f"[DRY-RUN] {source} -> {dest}")

    print(f"\n=== Summary ===")
    if commit:
        print(f"Moved: {moved}")
        print(f"Failed: {failed}")
        print(f"Skipped: {skipped}")
        print(f"Total: {moved + failed + skipped}")
    else:
        print(f"Would move {len(plan)} files")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Move files to new library"
    )
    ap.add_argument(
        "--plan",
        type=Path,
        default=Path("artifacts/reports/library_move_plan.csv"),
        help="Move plan CSV"
    )
    ap.add_argument(
        "--commit",
        action="store_true",
        help="Actually move files (dry-run by default)"
    )

    ns = ap.parse_args()

    if not ns.plan.exists():
        print(f"Plan not found: {ns.plan}")
        return 1

    # Load plan
    plan: List[Dict] = []
    with ns.plan.open('r') as f:
        reader = csv.DictReader(f)
        plan = list(reader)

    print(f"Loaded plan: {len(plan)} files")

    if not ns.commit:
        print("DRY-RUN mode (use --commit to actually move)")

    move_files(plan, commit=ns.commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
