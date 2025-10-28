#!/usr/bin/env python3
"""
check_dedupe_plan.py

Reads the dedupe report CSV and performs integrity checks on planned moves:
- Verifies source files exist.
- Runs 'flac -s -t <source>' to check FLAC integrity.
- Writes reports: plans_missing_sources.txt and _DEDUP_FLAC_TEST_FAILS.txt

Usage: python check_dedupe_plan.py [--csv /path/to/csv]
"""

import argparse
import csv
import os
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(description="Check integrity of dedupe plan sources.")
    parser.add_argument('--csv', default='/Volumes/dotad/MUSIC/_DEDUP_REPORT_20251028_014226.csv',
                        help='Path to the dedupe report CSV')
    args = parser.parse_args()

    csv_path = args.csv
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    missing_sources = []
    flac_fails = []

    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)  # skip header
        for row in reader:
            if len(row) < 16 or row[15] != 'plan':
                continue
            source = row[3]
            if not os.path.exists(source):
                missing_sources.append(source)
                continue
            # Run flac -t
            try:
                result = subprocess.run(['flac', '-s', '-t', source],
                                        capture_output=True, text=True, timeout=60)
                if result.returncode != 0:
                    flac_fails.append((source, result.stderr.strip()))
            except subprocess.TimeoutExpired:
                flac_fails.append((source, 'flac -t timed out'))
            except Exception as e:
                flac_fails.append((source, str(e)))

    # Write reports
    with open('plans_missing_sources.txt', 'w', encoding='utf-8') as f:
        for src in missing_sources:
            f.write(src + '\n')

    with open('_DEDUP_FLAC_TEST_FAILS.txt', 'w', encoding='utf-8') as f:
        for src, err in flac_fails:
            f.write(f"{src}: {err}\n")

    print(f"Checked {len([r for r in csv.reader(open(csv_path)) if len(r) >= 16 and r[15] == 'plan'])} planned sources.")
    print(f"Missing sources: {len(missing_sources)} (see plans_missing_sources.txt)")
    print(f"FLAC test failures: {len(flac_fails)} (see _DEDUP_FLAC_TEST_FAILS.txt)")

if __name__ == '__main__':
    main()