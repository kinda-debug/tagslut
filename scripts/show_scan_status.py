#!/usr/bin/env python3
"""Show file distribution across roots and metadata scan status."""
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".cache" / "file_dupes.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

roots = [
    '/Volumes/dotad/MUSIC',
    '/Volumes/dotad/Quarantine',
    '/Volumes/dotad/Garbage'
]

print("=== File Distribution by Root ===\n")

total_all = 0
total_scanned = 0
total_unscanned = 0

for root in roots:
    # Total files in this root
    cur.execute(
        "SELECT COUNT(*) FROM file_hashes WHERE file_path LIKE ?",
        (f"{root}%",)
    )
    total = cur.fetchone()[0]
    
    # Already scanned
    cur.execute(
        "SELECT COUNT(*) FROM file_hashes WHERE file_path LIKE ? AND metadata_scanned = 1",
        (f"{root}%",)
    )
    scanned = cur.fetchone()[0]
    
    unscanned = total - scanned
    
    print(f"{root}:")
    print(f"  Total:      {total:6,}")
    print(f"  Scanned:    {scanned:6,}")
    print(f"  Unscanned:  {unscanned:6,}")
    print()
    
    total_all += total
    total_scanned += scanned
    total_unscanned += unscanned

print("TOTALS:")
print(f"  All files:  {total_all:6,}")
print(f"  Scanned:    {total_scanned:6,}")
print(f"  Unscanned:  {total_unscanned:6,}")

conn.close()
