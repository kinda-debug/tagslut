#!/usr/bin/env python3
import argparse
import sqlite3
import sys
from pathlib import Path

try:
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path
except ModuleNotFoundError:  # pragma: no cover
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path

parser = argparse.ArgumentParser(description="Rank duplicates by checksum and path.")
parser.add_argument("--db", type=Path, required=False, help="SQLite DB path")
parser.add_argument("--allow-repo-db", action="store_true", help="Allow repo-local DB paths")
args = parser.parse_args()

repo_root = Path(__file__).resolve().parents[2]
resolution = resolve_db_path(
    args.db,
    config=get_config(),
    allow_repo_db=args.allow_repo_db,
    repo_root=repo_root,
    purpose="write",
    allow_create=False,
)

print("=== Ranking duplicates in:", resolution.path)

conn = open_db(resolution)
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
