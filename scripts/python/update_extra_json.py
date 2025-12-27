#!/usr/bin/env python3
import sqlite3
import json
from pathlib import Path

DB = "artifacts/db/library_canonical.db"
CSV = "artifacts/reports/canonical_health.csv"

con = sqlite3.connect(DB)
cur = con.cursor()

updated = 0
missing = 0

with open(CSV, "r", encoding="utf8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        # Format: path, score, info_dict
        try:
            path, score_str, info_str = line.split(",", 2)
        except ValueError:
            continue

        # Convert the Python-dict text into real JSON
        try:
            info_dict = eval(info_str)            # allowed here; trusted source
            info_json = json.dumps(info_dict)
        except Exception:
            info_json = "{}"

        # Update row
        cur.execute(
            "UPDATE library_files SET extra_json = ? WHERE path = ?;",
            (info_json, path)
        )

        if cur.rowcount == 0:
            missing += 1
        else:
            updated += 1

con.commit()
con.close()

print("Updated rows:", updated)
print("Paths not found in DB:", missing)
print("Done.")

