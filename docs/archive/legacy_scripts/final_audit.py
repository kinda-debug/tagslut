import sqlite3
import os
from pathlib import Path

db_path = "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_20260119/music.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("Calculating missing size...")
cursor.execute("SELECT path, size FROM files WHERE path LIKE '/Volumes/COMMUNE/M/Library_CANONICAL/%'")
rows = cursor.fetchall()

missing_count = 0
missing_size = 0
for row in rows:
    if not os.path.exists(row['path']):
        missing_count += 1
        missing_size += (row['size'] or 0)

print(f"Missing Files: {missing_count}")
print(f"Missing Size:  {missing_size / (1024**3):.2f} GB")

print("\nVerifying RECOVERY_TARGET as source...")
cursor.execute("""
    SELECT f2.path
    FROM files f1
    JOIN files f2 ON f1.sha256 = f2.sha256
    WHERE f1.path LIKE '/Volumes/COMMUNE/M/Library_CANONICAL/%'
    AND f1.path != f2.path
    AND f2.path LIKE '/Volumes/RECOVERY_TARGET/%'
    LIMIT 1000
""")
recovery_links = cursor.fetchall()
found_on_recovery = 0
for r in recovery_links:
    if os.path.exists(r['path']):
        found_on_recovery += 1

print(f"Availability on RECOVERY_TARGET (of sample): {found_on_recovery}/1000")

conn.close()
