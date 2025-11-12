#!/usr/bin/env python3
"""Analyze metadata differences for filename-based duplicates.

For files with the same name but different MD5, extract metadata to help decide
which version to keep.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path.home() / ".cache" / "file_dupes.db"


def get_flac_metadata(path: Path) -> Dict[str, str]:
    """Extract key FLAC metadata using metaflac."""
    metadata = {
        'file_size': path.stat().st_size,
        'title': '',
        'artist': '',
        'album': '',
        'date': '',
        'has_artwork': False,
    }
    
    try:
        # Get tags
        result = subprocess.run(
            ['metaflac', '--list', '--block-type=VORBIS_COMMENT', str(path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith('comment['):
                if 'TITLE=' in line:
                    metadata['title'] = line.split('TITLE=', 1)[1]
                elif 'ARTIST=' in line:
                    metadata['artist'] = line.split('ARTIST=', 1)[1]
                elif 'ALBUM=' in line:
                    metadata['album'] = line.split('ALBUM=', 1)[1]
                elif 'DATE=' in line:
                    metadata['date'] = line.split('DATE=', 1)[1]
        
        # Check for artwork
        result = subprocess.run(
            ['metaflac', '--list', '--block-type=PICTURE', str(path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        metadata['has_artwork'] = 'PICTURE' in result.stdout
        
    except Exception as e:
        metadata['error'] = str(e)
    
    return metadata


def analyze_filename_dupes(
    db_path: Path,
    limit: int = 0
) -> List[Dict]:
    """Analyze filename duplicates and their metadata differences."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Get all filename duplicates
    cur.execute("""
        SELECT file_path, file_md5, file_size
        FROM file_hashes
    """)
    
    filename_groups = {}
    for path_str, md5, size in cur.fetchall():
        path = Path(path_str)
        filename = path.name
        if filename not in filename_groups:
            filename_groups[filename] = []
        filename_groups[filename].append({
            'path': path_str,
            'md5': md5,
            'size': size
        })
    
    conn.close()
    
    # Filter to duplicates only
    dupes = {k: v for k, v in filename_groups.items() if len(v) > 1}
    
    print(f"Found {len(dupes)} filename groups with duplicates")
    
    results = []
    count = 0
    
    for filename, files in sorted(dupes.items()):
        if limit and count >= limit:
            break
        
        # Check if they have different MD5 (different content)
        unique_md5s = set(f['md5'] for f in files)
        if len(unique_md5s) == 1:
            # Same content, skip
            continue
        
        count += 1
        print(f"[{count}] Analyzing: {filename}")
        
        for file_info in files:
            path = Path(file_info['path'])
            if not path.exists():
                continue
            
            metadata = get_flac_metadata(path)
            
            results.append({
                'filename': filename,
                'path': file_info['path'],
                'md5': file_info['md5'],
                'size_bytes': file_info['size'],
                'path_depth': len(path.parts),
                'title': metadata.get('title', ''),
                'artist': metadata.get('artist', ''),
                'album': metadata.get('album', ''),
                'date': metadata.get('date', ''),
                'has_artwork': metadata.get('has_artwork', False),
                'error': metadata.get('error', '')
            })
    
    return results


def write_report(results: List[Dict], report_path: Path):
    """Write metadata analysis to CSV."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'filename', 'path', 'md5', 'size_bytes', 'path_depth',
            'title', 'artist', 'album', 'date', 'has_artwork', 'error'
        ])
        writer.writeheader()
        writer.writerows(results)
    
    print(f"\nMetadata analysis: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze metadata for filename duplicates"
    )
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument(
        "--report",
        type=Path,
        default="artifacts/reports/filename_dupes_metadata.csv"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit analysis to N groups (0=all)"
    )
    
    args = parser.parse_args()
    
    if not args.db.exists():
        print(f"Database not found: {args.db}")
        return 1
    
    results = analyze_filename_dupes(args.db, args.limit)
    
    if not results:
        print("No filename duplicates with different content found")
        return 0
    
    write_report(results, args.report)
    
    print(f"\nAnalyzed {len(results)} files from filename duplicate groups")
    print("Review the report to decide which versions to keep")
    
    return 0


if __name__ == "__main__":
    exit(main())
