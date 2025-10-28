#!/usr/bin/env python3
"""
apply_dedupe_plan.py

Applies the dedupe plan from CSV: moves planned sources to trash
destinations. Supports dry-run mode and batching for safety.

Usage:
  python apply_dedupe_plan.py --dry-run [--batch-size 50]
  python apply_dedupe_plan.py --commit [--batch-size 50] \
      [--csv /path/to/csv]

In dry-run: prints commands, checks sources, logs missing to
_DEDUP_MOVE_ERRORS.txt
In commit: executes moves, logs errors.
"""

import argparse
import csv
import os
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Apply dedupe plan moves.")
    parser.add_argument(
        '--csv',
        default='/Volumes/dotad/MUSIC/_DEDUP_REPORT_20251028_014226.csv',
        help='Path to the dedupe report CSV')
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Dry run: print commands without executing')
    parser.add_argument(
        '--commit', action='store_true',
        help='Commit: execute moves')
    parser.add_argument(
        '--batch-size', type=int, default=50,
        help='Process in batches of this size')
    args = parser.parse_args()

    if not args.dry_run and not args.commit:
        print("Error: Must specify --dry-run or --commit")
        sys.exit(1)

    csv_path = args.csv
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    # Collect plan rows
    plans = []
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) >= 17 and row[15] == 'plan':
                source = row[3]
                dest = row[16]
                plans.append((source, dest))

    print(f"Found {len(plans)} planned moves.")

    error_log = '_DEDUP_MOVE_ERRORS.txt'
    with open(error_log, 'w', encoding='utf-8') as err_f:
        batch_num = 0
        for i in range(0, len(plans), args.batch_size):
            batch = plans[i:i + args.batch_size]
            batch_num += 1
            print(f"Processing batch {batch_num} ({len(batch)} moves)...")
            for source, dest in batch:
                if not os.path.exists(source):
                    err_f.write(f"Missing source: {source}\n")
                    print(f"SKIP (missing): {source}")
                    continue
                if args.dry_run:
                    print(f"mv '{source}' '{dest}'")
                elif args.commit:
                    try:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.move(source, dest)
                        print(f"MOVED: {source} -> {dest}")
                    except Exception as e:
                        err_f.write(f"Move failed: {source} -> {dest}: {e}\n")
                        print(f"ERROR: {source} -> {dest}: {e}")
            if args.dry_run:
                print(f"Batch {batch_num} dry-run complete.")
            elif args.commit:
                print(f"Batch {batch_num} committed.")
                # Optional: pause or confirm
                # input("Press Enter to continue to next batch...")

    print(f"Done. Check {error_log} for errors.")


if __name__ == '__main__':
    main()
