#!/usr/bin/env python3
"""
verify_post_move.py

Post-move verification:
- Check that all 'keep' files still exist.
- Check that all 'plan' sources are moved (src gone, dest exists).
- Run flac -t on moved files to identify corrupted ones.
- Report counts and issues.
"""

import csv
import os
import subprocess
import sys

def main():
    csv_path = '/Volumes/dotad/MUSIC/_DEDUP_REPORT_20251028_014226.csv'
    if not os.path.exists(csv_path):
        print(f"Error: CSV not found: {csv_path}")
        sys.exit(1)

    keeps_ok = 0
    keeps_missing = []
    plans_moved_ok = 0
    plans_src_still_exists = []
    plans_dest_missing = []
    moved_corrupt = []

    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) < 15:
                continue
            if row[14] == 'keep':
                path = row[3]
                if os.path.exists(path):
                    keeps_ok += 1
                else:
                    keeps_missing.append(path)
            elif len(row) >= 17 and row[15] == 'plan':
                src = row[3]
                dest = row[16]
                if os.path.exists(src):
                    plans_src_still_exists.append(src)
                elif os.path.exists(dest):
                    plans_moved_ok += 1
                    # Check flac -t
                    try:
                        result = subprocess.run(['flac', '-s', '-t', dest],
                                                capture_output=True, text=True, timeout=30)
                        if result.returncode != 0:
                            moved_corrupt.append((dest, result.stderr.strip()))
                    except Exception as e:
                        moved_corrupt.append((dest, str(e)))
                else:
                    plans_dest_missing.append((src, dest))

    print(f"Keeps: {keeps_ok} intact, {len(keeps_missing)} missing")
    print(f"Moves: {plans_moved_ok} successful, {len(plans_src_still_exists)} src still exists, {len(plans_dest_missing)} dest missing")
    print(f"Moved corrupt: {len(moved_corrupt)}")

    with open('post_move_verification.txt', 'w', encoding='utf-8') as f:
        f.write("Missing keeps:\n")
        for p in keeps_missing:
            f.write(p + '\n')
        f.write("\nSrc still exists:\n")
        for p in plans_src_still_exists:
            f.write(p + '\n')
        f.write("\nDest missing:\n")
        for s, d in plans_dest_missing:
            f.write(f"{s} -> {d}\n")
        f.write("\nMoved corrupt:\n")
        for d, err in moved_corrupt:
            f.write(f"{d}: {err}\n")

    print("Details in post_move_verification.txt")

if __name__ == '__main__':
    main()