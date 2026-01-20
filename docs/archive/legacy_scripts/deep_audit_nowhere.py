import sqlite3
import os
from pathlib import Path

db_path = "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_20260119/music.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("Deep audit of 22 'nowhere' files...")
cursor.execute("SELECT path, sha256 FROM files WHERE path LIKE '/Volumes/COMMUNE/M/Library_CANONICAL/%'")
rows = cursor.fetchall()

missing_files = []
for row in rows:
    if not os.path.exists(row['path']):
        missing_files.append((row['path'], row['sha256']))

nowhere_files = []
for path, sha256 in missing_files:
    cursor.execute("SELECT path FROM files WHERE sha256 = ? AND path != ?", (sha256, path))
    others = cursor.fetchall()

    found_any = False
    for (other_path,) in others:
        if os.path.exists(other_path):
            found_any = True
            break

    if not found_any:
        nowhere_files.append((path, sha256))
        if len(nowhere_files) >= 20:
            break

print(f"\nSample of files with NO surviving copies on known volumes:")
for path, sha256 in nowhere_files:
    print(f"  Missing Path: {path}")
    print(f"  SHA256:       {sha256}")

    # Let's see if the hash exists in ANY path, even if the file is gone,
    # to see where it USED to be.
    cursor.execute("SELECT path, zone FROM files WHERE sha256 = ?", (sha256,))
    all_known = cursor.fetchall()
    print("  DB History:")
    for r in all_known:
        status = "EXISTS" if os.path.exists(r['path']) else "GONE"
        print(f"    - [{status}] [{r['zone']}] {r['path']}")
    print("-" * 40)

conn.close()
