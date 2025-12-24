#!/usr/bin/env python3
import os
import sqlite3
import json
import shutil
import subprocess
from pathlib import Path
import tempfile

DB_PATH = "artifacts/db/library_canonical.db"
SCAN_DB = "artifacts/db/tmp_fix.sqlite"

def run(cmd):
    subprocess.run(cmd, shell=True, check=True)

def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
        SELECT path FROM library_files
        WHERE extra_json IS NULL OR extra_json = ''
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"Files to fix: {total}")

    for idx, (path,) in enumerate(rows, start=1):

        if not os.path.exists(path):
            print(f"[{idx}/{total}] Missing on disk: {path}")
            continue

        # Create a temporary directory for this file only
        with tempfile.TemporaryDirectory(prefix="rescan_") as tmpdir:
            base = os.path.basename(path)
            tmp_path = os.path.join(tmpdir, base)

            # Copy file to temp
            try:
                shutil.copy2(path, tmp_path)
            except OSError as e:
                print(f"[{idx}/{total}] Copy failed: {path} -> {e}")
                continue

            # Scan the temp directory
            try:
                run(
                    f"python3 -m dedupe.cli scan-library "
                    f"--root '{tmpdir}' --out '{SCAN_DB}' --progress"
                )
            except Exception as e:
                print(f"[{idx}/{total}] Scanner failed: {path} -> {e}")
                continue

            # Load metadata from the scan DB
            scan_con = sqlite3.connect(SCAN_DB)
            scan_cur = scan_con.cursor()
            scan_cur.execute("SELECT tags_json, extra_json FROM library_files LIMIT 1")
            row = scan_cur.fetchone()
            scan_con.close()

            if not row:
                print(f"[{idx}/{total}] No metadata returned for: {path}")
                continue

            tags_json, extra_json = row

            # Update the original DB row
            cur.execute("""
                UPDATE library_files
                SET tags_json = ?, extra_json = ?
                WHERE path = ?
            """, (tags_json, extra_json, path))
            con.commit()

            print(f"[{idx}/{total}] Updated: {path}")

    con.close()
    print("Fix completed.")

if __name__ == "__main__":
    main()
