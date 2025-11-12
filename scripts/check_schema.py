#!/usr/bin/env python3
"""Quick schema checker"""
import sqlite3
from pathlib import Path

conn = sqlite3.connect(Path.home() / '.cache' / 'file_dupes.db')
cur = conn.cursor()
cur.execute('PRAGMA table_info(file_hashes)')
print("Current schema:")
for row in cur.fetchall():
    print(f"  {row[1]:20} {row[2]:10}")

# Check how many files have metadata
cur.execute("SELECT COUNT(*) FROM file_hashes WHERE metadata_scanned = 1")
print(f"\nFiles with metadata: {cur.fetchone()[0]}")
