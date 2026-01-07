#!/usr/bin/env python3
"""
Resumable scanner for NOT_SCANNED files.
Queries database for NOT_SCANNED files, writes them to a file list,
and uses the existing scanner tool with --paths-from-file.
Safe to interrupt and resume - always picks up where it left off.
"""
import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

try:
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path
except ModuleNotFoundError:  # pragma: no cover
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path

BATCH_SIZE = 1000
PATHS_FILE = "/tmp/not_scanned_paths.txt"

def get_not_scanned_count(db_resolution, library, zone):
    """Get count of NOT_SCANNED files."""
    conn = open_db(db_resolution)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) 
        FROM files 
        WHERE library = ? AND zone = ? AND checksum LIKE 'NOT_SCANNED%'
    """, (library, zone))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_not_scanned_batch(db_resolution, library, zone, batch_size):
    """Get batch of NOT_SCANNED file paths."""
    conn = open_db(db_resolution)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT path
        FROM files 
        WHERE library = ? AND zone = ? AND checksum LIKE 'NOT_SCANNED%'
        ORDER BY path
        LIMIT ?
    """, (library, zone, batch_size))
    
    paths = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    return paths

def scan_batch(db_path, paths, library, zone, allow_repo_db):
    """Scan a batch of files using the existing scanner tool."""
    if not paths:
        return False
    
    # Write paths to file
    Path(PATHS_FILE).write_text("\n".join(paths))
    
    print(f"\n{'='*70}")
    print(f"Scanning {len(paths)} NOT_SCANNED files from {library}/{zone}")
    print(f"{'='*70}\n")
    
    # Get dummy library path (won't be used with --paths-from-file)
    dummy_path = Path(paths[0]).parent
    
    # Run the scanner
    cmd = [
        "python3", "tools/integrity/scan.py",
        "--db", db_path,
        "--paths-from-file", PATHS_FILE,
        "--library", library,
        "--zone", zone
    ]
    if allow_repo_db:
        cmd.append("--allow-repo-db")
    
    result = subprocess.run(cmd)
    return result.returncode == 0

def main():
    parser = argparse.ArgumentParser(
        description="Resumable scanner for NOT_SCANNED files"
    )
    parser.add_argument("library", help="Library tag")
    parser.add_argument("zone", help="Zone tag")
    parser.add_argument("--db", help="SQLite DB path (or set DEDUPE_DB)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--allow-repo-db", action="store_true", help="Allow repo-local DB paths")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    try:
        db_resolution = resolve_db_path(
            args.db,
            config=get_config(),
            allow_repo_db=args.allow_repo_db,
            repo_root=repo_root,
            purpose="read",
            allow_create=False,
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    db_path = str(db_resolution.path)

    library = args.library
    zone = args.zone
    batch_size = args.batch_size
    allow_repo_db = args.allow_repo_db
    
    total_scanned = 0
    batch_num = 0
    
    while True:
        # Always query fresh from database (resumable!)
        remaining = get_not_scanned_count(db_resolution, library, zone)
        
        if remaining == 0:
            print(f"\n{'='*70}")
            print(f"✓ ALL FILES SCANNED!")
            print(f"Total batches: {batch_num}")
            print(f"{'='*70}\n")
            break
        
        batch_num += 1
        print(f"\n{'='*70}")
        print(f"BATCH {batch_num}: {remaining} NOT_SCANNED files remaining")
        print(f"{'='*70}")
        
        # Get next batch
        paths = get_not_scanned_batch(db_resolution, library, zone, batch_size)
        
        if not paths:
            break
        
        # Scan this batch
        success = scan_batch(db_path, paths, library, zone, allow_repo_db)
        
        if not success:
            print(f"\n⚠️ Batch {batch_num} failed. Safe to resume - run this script again.")
            sys.exit(1)
        
        print(f"\n✓ Batch {batch_num} complete")

if __name__ == "__main__":
    main()
