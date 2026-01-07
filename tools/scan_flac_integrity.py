#!/usr/bin/env python3
"""
Scan FLAC files for integrity using 'flac -t' and update database.

Usage:
    # Scan all files in database
    tools/scan_flac_integrity.py --db "$DEDUPE_DB"

    # Scan only files without integrity check yet
    tools/scan_flac_integrity.py --db "$DEDUPE_DB" --unchecked-only

    # Parallel scan (faster)
    tools/scan_flac_integrity.py --db "$DEDUPE_DB" --parallel 8

Requires:
  - flac command-line tool (brew install flac)
"""
import argparse
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Allow running this file directly without installing the package.
try:
    from dedupe.core.integrity import classify_flac_integrity
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path
except ModuleNotFoundError:  # pragma: no cover
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    from dedupe.core.integrity import classify_flac_integrity
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path


def ensure_integrity_column(conn: sqlite3.Connection):
    """Add integrity columns if missing."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(library_files)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    
    if "flac_ok" not in existing_cols:
        print("Adding column: flac_ok")
        cursor.execute("ALTER TABLE library_files ADD COLUMN flac_ok INTEGER")
    if "integrity_state" not in existing_cols:
        print("Adding column: integrity_state")
        cursor.execute("ALTER TABLE library_files ADD COLUMN integrity_state TEXT")
    conn.commit()


def test_flac_integrity(path: str) -> tuple[str, str]:
    """
    Test FLAC file integrity using 'flac -t'.

    Returns:
        (path, integrity_state) tuple
    """
    try:
        state, _ = classify_flac_integrity(Path(path))
        return (path, state)
    except RuntimeError:
        print("ERROR: 'flac' command not found. Install with: brew install flac")
        sys.exit(1)
    except Exception as e:
        print(f"WARN: Error testing {path}: {e}")
        return (path, "corrupt")


def update_integrity_result(conn: sqlite3.Connection, path: str, integrity_state: str):
    """Update integrity result in database."""
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE library_files SET flac_ok = ?, integrity_state = ? WHERE path = ?",
        (1 if integrity_state == "valid" else 0, integrity_state, path)
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Scan FLAC integrity and update database"
    )
    parser.add_argument(
        "--db",
        required=False,
        type=Path,
        help="SQLite database path"
    )
    parser.add_argument(
        "--allow-repo-db",
        action="store_true",
        help="Allow writing to a repo-local database path",
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
    
    repo_root = Path(__file__).resolve().parents[1]
    try:
        resolution = resolve_db_path(
            args.db,
            config=get_config(),
            allow_repo_db=args.allow_repo_db,
            repo_root=repo_root,
            purpose="write",
            allow_create=False,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    print(f"Database: {resolution.path}")
    print(f"Workers: {args.parallel}")
    print()
    
    conn = open_db(resolution)
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
    recoverable_count = 0
    corrupt_count = 0
    
    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {executor.submit(test_flac_integrity, p): p for p in paths}
        
        for idx, future in enumerate(as_completed(futures), 1):
            path, integrity_state = future.result()
            update_integrity_result(conn, path, integrity_state)
            
            if integrity_state == "valid":
                ok_count += 1
                status = "✓"
            elif integrity_state == "recoverable":
                recoverable_count += 1
                status = "⚠ RECOVERABLE"
            else:
                corrupt_count += 1
                status = "✗ CORRUPT"
                print(f"\n{status}: {path}")
            
            # Progress
            if idx % 100 == 0 or idx == total:
                print(
                    f"\r[{idx}/{total}] OK: {ok_count}, Recoverable: {recoverable_count}, "
                    f"Corrupt: {corrupt_count}",
                    end="",
                )
    
    print("\n")
    print("="*60)
    print("INTEGRITY SCAN COMPLETE")
    print("="*60)
    print(f"Total scanned:  {total:6d}")
    print(f"Valid:          {ok_count:6d}  ({ok_count*100//total if total else 0}%)")
    print(
        f"Recoverable:    {recoverable_count:6d}  "
        f"({recoverable_count*100//total if total else 0}%)"
    )
    print(f"Corrupt:        {corrupt_count:6d}  ({corrupt_count*100//total if total else 0}%)")
    print("="*60)
    
    conn.close()


if __name__ == "__main__":
    main()
