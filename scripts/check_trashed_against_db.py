#!/usr/bin/env python3
import os
import sqlite3
import hashlib
import sys
import csv

DB_PATH = "artifacts/db/library.db"
INPUT_LIST = "artifacts/tmp/trashed_flacs.txt"
OUT_CSV = "artifacts/reports/trashed_db_matches.csv"

def sha1_of_file(path, buf_size=65536):
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(buf_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None

# --- MAIN ---
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

with open(INPUT_LIST, "r") as f:
    trashed_paths = [x.strip() for x in f if x.strip()]

rows = []

for p in trashed_paths:
    checksum = sha1_of_file(p)
    if not checksum:
        rows.append([p, "UNKNOWN", "", ""])
        continue

    cur.execute("SELECT path FROM library_files WHERE checksum=?", (checksum,))
    matches = cur.fetchall()

    if matches:
        for (orig,) in matches:
            rows.append([p, "DB_MATCH", orig, checksum])
    else:
        rows.append([p, "NOT_IN_DB", "", checksum])

# write report
os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)

with open(OUT_CSV, "w", newline="", encoding="utf-8") as out:
    w = csv.writer(out)
    w.writerow(["trashed_path", "status", "db_original_path", "checksum"])
    for r in rows:
        w.writerow(r)

print("Done. Report written to:", OUT_CSV)
