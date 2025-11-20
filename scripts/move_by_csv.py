#!/usr/bin/env python3
import csv
import os
import shutil
import sys

if len(sys.argv) < 3:
    print("Usage: move_by_csv.py decisions.csv DEST_DIR")
    sys.exit(1)

csv_path = sys.argv[1]
dest_root = sys.argv[2]

print("=== MOVE BY CSV (SAFE MODE) ===")
print(f"Decisions:  {csv_path}")
print(f"Quarantine: {dest_root}\n")

moved = 0
skipped = 0
missing = 0

os.makedirs(dest_root, exist_ok=True)

with open(csv_path, newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        action = row.get("action", "").strip().upper()
        path = row.get("path", "").strip().strip('"')

        if action != "MOVE":
            skipped += 1
            continue

        # Accept either files or directories depending on what's present
        if not (os.path.isfile(path) or os.path.isdir(path)):
            missing += 1
            print(f"Missing: {path}")
            continue

        # If it's a directory, move the directory into dest_root preserving its basename
        base = os.path.basename(path.rstrip('/'))
        dst = os.path.join(dest_root, base)

        try:
            shutil.move(path, dst)
            moved += 1
        except Exception as e:
            print(f"Error moving {path}: {e}")

print("\n=== SUMMARY ===")
print(f"Moved files/dirs:   {moved}")
print(f"Skipped rows:      {skipped}")
print(f"Missing files/dirs:{missing}")
print("================")
