#!/usr/bin/env python3
"""
Scan FLAC files for integrity using 'flac -t' and update database.

Hard rule: flac_ok=0 → auto-DROP (corrupt files are never kept)

Usage:
  # Scan all files in database
  tools/scan_flac_integrity.py --db ~/Projects/_audit/sad_hash.sqlite

  # Scan only files without integrity check yet
  tools/scan_flac_integrity.py --db ~/Projects/_audit/sad_hash.sqlite --unchecked-only

  # Parallel scan (faster)
  tools/scan_flac_integrity.py --db ~/Projects/_audit/sad_hash.sqlite --parallel 8

Requires:
  - flac command-line tool (brew install flac)
"""
import argparse
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def ensure_integrity_column(conn: sqlite3.Connection):
    """Add flac_ok column if missing."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(library_files)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    
    if "flac_ok" not in existing_cols:
        print("Adding column: flac_ok")
        cursor.execute("ALTER TABLE library_files ADD COLUMN flac_ok INTEGER")
        conn.commit()


def test_flac_integrity(path: str) -> tuple[str, bool]:
    """
    Test FLAC file integrity using 'flac -t'.
    
    Returns:
        (path, is_ok) tuple
    """
    try:
        result = subprocess.run(
            ["flac", "-t", "-s", path],  # -s = silent
            capture_output=True,
            timeout=30
        )
        return (path, result.returncode == 0)
    except subprocess.TimeoutExpired:
        return (path, False)
    except FileNotFoundError:
        print("ERROR: 'flac' command not found. Install with: brew install flac")
        sys.exit(1)
    except Exception as e:
        print(f"WARN: Error testing {path}: {e}")
        return (path, False)


def update_integrity_result(conn: sqlite3.Connection, path: str, is_ok: bool):
    """Update integrity result in database."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE library_files SET flac_ok = ? WHERE path = ?",
        (1 if is_ok else 0, path)
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Scan FLAC integrity and update database"
    )
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        help="SQLite database path"
    )
    parser.add_argument(
        "--unchecked-only",
        action="store_true",
        help="Only scan files not yet checked"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)"
    )
    
    args = parser.parse_args()
    
    if not args.db.exists():
        print(f"ERROR: Database not found: {args.db}")
        sys.exit(1)
    
    print(f"Database: {args.db}")
    print(f"Workers: {args.parallel}")
    print()
    
    conn = sqlite3.connect(args.db)
    ensure_integrity_column(conn)
    
    # Load files to check
    cursor = conn.cursor()
    if args.unchecked_only:
        query = "SELECT path FROM library_files WHERE flac_ok IS NULL"
    else:
        query = "SELECT path FROM library_files"
    
    cursor.execute(query)
    paths = [row[0] for row in cursor.fetchall()]
    
    total = len(paths)
    print(f"Checking {total} FLAC files...")
    
    if total == 0:
        print("No files to check")
        conn.close()
        return
    
    # Process in parallel
    ok_count = 0
    corrupt_count = 0
    
    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {executor.submit(test_flac_integrity, p): p for p in paths}
        
        for idx, future in enumerate(as_completed(futures), 1):
            path, is_ok = future.result()
            update_integrity_result(conn, path, is_ok)
            
            if is_ok:
                ok_count += 1
                status = "✓"
            else:
                corrupt_count += 1
                status = "✗ CORRUPT"
                print(f"\n{status}: {path}")
            
            # Progress
            if idx % 100 == 0 or idx == total:
                print(f"\r[{idx}/{total}] OK: {ok_count}, Corrupt: {corrupt_count}", end="")
    
    print("\n")
    print("="*60)
    print("INTEGRITY SCAN COMPLETE")
    print("="*60)
    print(f"Total scanned:  {total:6d}")
    print(f"Valid:          {ok_count:6d}  ({ok_count*100//total if total else 0}%)")
    print(f"Corrupt:        {corrupt_count:6d}  ({corrupt_count*100//total if total else 0}%)")
    print("="*60)
    
    if corrupt_count > 0:
        print("\n⚠️  Corrupt files will be auto-flagged DROP in keeper recommendations")
    
    conn.close()


if __name__ == "__main__":
    main()
