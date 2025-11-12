#!/usr/bin/env python3
"""Find files with identical names (filename-based duplicates) across roots.

This matches Dupeguru's filename mode: files are considered duplicates if they
have the same filename, regardless of their content (MD5) or location.

Usage:
    python scripts/find_filename_dupes.py --report artifacts/reports/filename_dupes.csv
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

DB_PATH = Path.home() / ".cache" / "file_dupes.db"


def find_filename_duplicates(db_path: Path) -> Dict[str, List[str]]:
    """Group files by basename (filename), return groups with 2+ files."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Group all files by their basename
    filename_groups = defaultdict(list)
    
    cur.execute("SELECT file_path FROM file_hashes")
    for (path_str,) in cur.fetchall():
        path = Path(path_str)
        filename = path.name
        filename_groups[filename].append(path_str)
    
    conn.close()
    
    # Filter to only groups with duplicates
    return {name: paths for name, paths in filename_groups.items() if len(paths) > 1}


def write_report(duplicates: Dict[str, List[str]], report_path: Path):
    """Write filename duplicates to CSV."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['filename', 'count', 'paths'])
        
        for filename in sorted(duplicates.keys()):
            paths = duplicates[filename]
            writer.writerow([filename, len(paths), ' | '.join(paths)])
    
    print(f"Filename duplicates report: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Find filename-based duplicates (same name, any content)"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Database path (default: {DB_PATH})"
    )
    parser.add_argument(
        "--report",
        type=Path,
        default="artifacts/reports/filename_dupes.csv",
        help="Output CSV report path"
    )
    
    args = parser.parse_args()
    
    if not args.db.exists():
        print(f"Database not found: {args.db}")
        print("Run scan_all_roots.py first to populate the database")
        return 1
    
    print("Finding filename duplicates...")
    duplicates = find_filename_duplicates(args.db)
    
    total_groups = len(duplicates)
    total_files = sum(len(paths) for paths in duplicates.values())
    total_extras = total_files - total_groups  # files to delete if keeping 1 per group
    
    print(f"\n=== FILENAME DUPLICATE SUMMARY ===")
    print(f"Duplicate filename groups: {total_groups}")
    print(f"Total files with duplicate names: {total_files}")
    print(f"Files to review/delete: {total_extras}")
    
    write_report(duplicates, args.report)
    
    return 0


if __name__ == "__main__":
    exit(main())
