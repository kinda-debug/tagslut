#!/usr/bin/env python3
"""
Sample deleted files from Garbage and compare with kept MUSIC copies.
"""
import csv
import os
import random
from pathlib import Path

# Read the move plan
move_plan_path = Path('artifacts/reports/library_move_plan.csv')
with open(move_plan_path) as f:
    reader = csv.DictReader(f)
    rows = list(reader)

# Group by MD5 to find what was kept vs deleted
md5_to_kept = {}
garbage_files = []

for row in rows:
    md5 = row['md5']
    source_root = row['source_root']
    source_path = row['source']
    
    if md5 not in md5_to_kept:
        md5_to_kept[md5] = row
    
    if source_root == 'Garbage':
        garbage_files.append((md5, source_path))

print(f"Total files in move plan: {len(rows)}")
print(f"Files from Garbage folder: {len(garbage_files)}")
print()

# Sample 10 random Garbage files
samples = random.sample(garbage_files, min(10, len(garbage_files)))

print("=" * 100)
print("SAMPLING 10 DELETED GARBAGE FILES")
print("=" * 100)

for i, (md5, garbage_path) in enumerate(samples, 1):
    kept_row = md5_to_kept[md5]
    kept_path = kept_row['source']
    kept_source = kept_row['source_root']
    
    garbage_exists = os.path.exists(garbage_path)
    kept_exists = os.path.exists(kept_path)
    
    print(f"\n[SAMPLE {i}] MD5: {md5[:16]}")
    print(f"  DELETED (Garbage):  {garbage_path}")
    print(f"    - Exists: {garbage_exists}")
    if garbage_exists:
        size_mb = os.path.getsize(garbage_path) / (1024*1024)
        print(f"    - Size: {size_mb:.2f} MB")
    
    print(f"  KEPT ({kept_source}):  {kept_path}")
    print(f"    - Exists: {kept_exists}")
    if kept_exists:
        size_mb = os.path.getsize(kept_path) / (1024*1024)
        print(f"    - Size: {size_mb:.2f} MB")

print("\n" + "=" * 100)
print("VERIFICATION COMPLETE")
print("=" * 100)
