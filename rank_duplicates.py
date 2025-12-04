#!/usr/bin/env python3
import sqlite3
from pathlib import Path

REPO = Path.home() / "dedupe_repo_reclone"
DB_PATH = REPO / "artifacts/db/library_final.db"

print("=== Ranking duplicates in:", DB_PATH)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Reset duplicate_rank for all rows
cur.execute("""
UPDATE library_files
SET duplicate_rank = NULL
WHERE duplicate_rank IS NOT NULL;
""")
conn.commit()

print("=== Fetching groups by checksum…")
cur.execute("""
SELECT checksum, COUNT(*) AS c
FROM library_files
WHERE checksum IS NOT NULL
GROUP BY checksum
HAVING c > 1;
""")
groups = cur.fetchall()
print(f"Found {len(groups)} duplicate checksum groups")

for g in groups:
    checksum = g["checksum"]
    cur.execute("""
        SELECT path
        FROM library_files
        WHERE checksum = ?
        ORDER BY path COLLATE NOCASE;
    """, (checksum,))
    rows = cur.fetchall()
    if not rows:
        continue
    # First lexicographically sorted path becomes canonical
    canonical_path = rows[0]["path"]
    cur.execute("""
        UPDATE library_files
        SET duplicate_rank = 1
        WHERE path = ?;
    """, (canonical_path,))
    # Others get rank 2..n
    for idx, row in enumerate(rows[1:], start=2):
        cur.execute("""
            UPDATE library_files
            SET duplicate_rank = ?
            WHERE path = ?;
        """, (idx, row["path"]))
conn.commit()
print("=== Ranking complete ===")
