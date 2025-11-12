import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".cache" / "file_dupes.db"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=== Current Schema ===")
cur.execute("PRAGMA table_info(file_hashes)")
for row in cur.fetchall():
    print(f"{row[0]:3} {row[1]:25} {row[2]:15} notnull={row[3]} default={row[4]}")

print("\n=== Files with metadata ===")
cur.execute("SELECT COUNT(*) FROM file_hashes WHERE metadata_scanned = 1")
print(f"Scanned: {cur.fetchone()[0]}")

print("\n=== Sample metadata (1 file) ===")
cur.execute("SELECT file_path, artist, album, vorbis_tags FROM file_hashes WHERE metadata_scanned = 1 LIMIT 1")
row = cur.fetchone()
if row:
    print(f"Path: {row[0]}")
    print(f"Artist (old): {row[1]}")
    print(f"Album (old): {row[2]}")
    print(f"Vorbis (new): {row[3]}")

conn.close()
