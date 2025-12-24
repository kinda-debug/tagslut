#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sqlite3

DIRS = [
    "/Volumes/dotad/QUARANTINE_AUTO_GLOBAL",
    "/Volumes/dotad/G_DUPEGURU",
    "/Volumes/dotad/NEW_LIBRARY",
    "/Volumes/dotad/NEW_LIBRARY_CLEAN",
    "/Volumes/dotad/flaccid",
    "/Volumes/dotad/flacslut",
    "/Volumes/dotad/sub-optimal",
    "/Volumes/dotad/NEW_MUSIC",
]

SCAN_DB = "artifacts/db/tmp_scan.sqlite"
CANON_DB = "artifacts/db/library_canonical.db"

def run_scan(path):
    print(f"Scanning: {path}")
    subprocess.run([
        "python3", "-m", "dedupe.cli", "scan-library",
        "--root", path,
        "--out", SCAN_DB
    ], check=True)

def merge_scan():
    conn = sqlite3.connect(CANON_DB)
    cur = conn.cursor()
    cur.execute(f"ATTACH '{SCAN_DB}' AS scan;")
    cur.execute("""
        INSERT INTO library_files (path, tags_json, extra_json)
        SELECT path, tags_json, extra_json FROM scan.library_files;
    """)
    cur.execute("DETACH scan;")
    conn.commit()
    conn.close()
    print("Merged into canonical DB.")

def main():
    for d in DIRS:
        run_scan(d)
        merge_scan()
        Path(SCAN_DB).unlink(missing_ok=True)

if __name__ == "__main__":
    main()
