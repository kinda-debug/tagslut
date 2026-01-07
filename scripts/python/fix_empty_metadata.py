#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path
except ModuleNotFoundError:  # pragma: no cover
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path

def run(cmd):
    subprocess.run(cmd, shell=True, check=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=False, help="Target library DB path")
    parser.add_argument("--scan-db", type=Path, required=True, help="Temporary scan DB path")
    parser.add_argument("--create-db", action="store_true", help="Allow creating the scan DB file")
    parser.add_argument("--allow-repo-db", action="store_true", help="Allow repo-local DB paths")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    target_resolution = resolve_db_path(
        args.db,
        config=get_config(),
        allow_repo_db=args.allow_repo_db,
        repo_root=repo_root,
        purpose="write",
        allow_create=False,
    )
    scan_resolution = resolve_db_path(
        args.scan_db,
        config=get_config(),
        allow_repo_db=args.allow_repo_db,
        repo_root=repo_root,
        purpose="write",
        allow_create=args.create_db,
        source_label="explicit",
    )

    con = open_db(target_resolution)
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
                scan_cmd = [
                    "python3",
                    "-m",
                    "dedupe.cli",
                    "scan-library",
                    "--root",
                    tmpdir,
                    "--db",
                    str(scan_resolution.path),
                    "--progress",
                ]
                if args.create_db:
                    scan_cmd.append("--create-db")
                if args.allow_repo_db:
                    scan_cmd.append("--allow-repo-db")
                run(" ".join(scan_cmd))
            except Exception as e:
                print(f"[{idx}/{total}] Scanner failed: {path} -> {e}")
                continue

            # Load metadata from the scan DB
            scan_con = open_db(
                resolve_db_path(
                    scan_resolution.path,
                    config=get_config(),
                    allow_repo_db=args.allow_repo_db,
                    repo_root=repo_root,
                    purpose="read",
                    allow_create=False,
                    source_label="explicit",
                )
            )
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
