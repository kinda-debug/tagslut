#!/usr/bin/env python3
import argparse
import json
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

parser = argparse.ArgumentParser(description="Update extra_json from a CSV report.")
parser.add_argument("--db", type=Path, required=False, help="SQLite DB path")
parser.add_argument("--csv", type=Path, required=True, help="CSV report path")
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

con = open_db(resolution)
cur = con.cursor()

updated = 0
missing = 0

with args.csv.open("r", encoding="utf8") as f:
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
