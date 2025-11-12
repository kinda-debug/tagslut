#!/usr/bin/env python3
"""Scan and store comprehensive FLAC metadata in database.

Extends the file_hashes table with metadata columns for:
- Vorbis comments (artist, album, title, date, genre, etc.)
- Audio properties (bitrate, sample rate, channels, duration)
- Artwork presence
- Encoder info

Usage:
    python scripts/scan_metadata.py /Volumes/dotad/MUSIC
    python scripts/scan_metadata.py --all-roots  # scan MUSIC, Quarantine, Garbage
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import json
from pathlib import Path
from typing import Dict, Optional
import sys

DB_PATH = Path.home() / ".cache" / "file_dupes.db"


def init_metadata_schema(conn: sqlite3.Connection):
    """Add metadata columns to file_hashes table."""
    cur = conn.cursor()
    
    # Check if metadata columns exist
    cur.execute("PRAGMA table_info(file_hashes)")
    existing_cols = {row[1] for row in cur.fetchall()}
    
    # Add columns for comprehensive metadata storage
    metadata_cols = [
        ("vorbis_tags", "TEXT"),  # JSON: all Vorbis comments
        ("audio_properties", "TEXT"),  # JSON: ffprobe audio stream info
        ("format_info", "TEXT"),  # JSON: ffprobe format container info
        ("has_artwork", "INTEGER"),  # 0/1 boolean
        ("artwork_count", "INTEGER"),  # number of embedded pictures
        ("metadata_scanned", "INTEGER DEFAULT 0"),
    ]
    
    for col_name, col_type in metadata_cols:
        if col_name not in existing_cols:
            print(f"Adding column: {col_name}")
            cur.execute(
                f"ALTER TABLE file_hashes ADD COLUMN {col_name} {col_type}"
            )
    
    conn.commit()


def extract_flac_metadata(path: Path) -> Optional[Dict]:
    """Extract ALL FLAC metadata using metaflac and ffprobe."""
    if not path.exists():
        return None
    
    metadata = {
        'vorbis_tags': {},
        'audio_properties': {},
        'format_info': {},
        'has_artwork': 0,
        'artwork_count': 0,
    }
    
    # Get ALL Vorbis comments using metaflac
    try:
        result = subprocess.run(
            ['metaflac', '--export-tags-to=-', str(path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        tags = {}
        for line in result.stdout.splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                # Store all tags, handle duplicates as lists
                if key in tags:
                    if isinstance(tags[key], list):
                        tags[key].append(value)
                    else:
                        tags[key] = [tags[key], value]
                else:
                    tags[key] = value
        
        metadata['vorbis_tags'] = tags
        
        # Count artwork blocks
        result = subprocess.run(
            ['metaflac', '--list', '--block-type=PICTURE', str(path)],
            capture_output=True,
            text=True,
            timeout=5
        )
        picture_count = result.stdout.count('METADATA block #')
        metadata['has_artwork'] = 1 if picture_count > 0 else 0
        metadata['artwork_count'] = picture_count
        
    except Exception as e:
        print(f"  metaflac error for {path.name}: {e}", file=sys.stderr)
    
    # Get ALL audio/format properties using ffprobe
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-show_format', '-show_streams',
                '-of', 'json',
                str(path)
            ],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        data = json.loads(result.stdout)
        
        # Store complete stream info
        if 'streams' in data and data['streams']:
            metadata['audio_properties'] = data['streams'][0]
        
        # Store complete format/container info
        if 'format' in data:
            metadata['format_info'] = data['format']
            
    except Exception as e:
        print(f"  ffprobe error for {path.name}: {e}", file=sys.stderr)
    
    return metadata


def scan_and_update_metadata(
    root: Path,
    conn: sqlite3.Connection,
    limit: int = 0
):
    """Scan files and update metadata in database."""
    cur = conn.cursor()
    
    # Get files that need metadata scanning
    cur.execute("""
        SELECT file_path FROM file_hashes
        WHERE file_path LIKE ?
        AND (metadata_scanned IS NULL OR metadata_scanned = 0)
    """, (f"{root}%",))
    
    files_to_scan = [Path(row[0]) for row in cur.fetchall()]
    
    if not files_to_scan:
        print(f"No files to scan under {root}")
        return
    
    if limit:
        files_to_scan = files_to_scan[:limit]
    
    print(f"Scanning metadata for {len(files_to_scan)} files...")
    
    for idx, path in enumerate(files_to_scan, 1):
        if idx % 100 == 0:
            print(f"[{idx}/{len(files_to_scan)}] {path.name}")
            conn.commit()
        
        metadata = extract_flac_metadata(path)
        
        if metadata:
            # Convert dicts to JSON strings for storage
            vorbis_json = json.dumps(metadata.get('vorbis_tags', {}))
            audio_json = json.dumps(metadata.get('audio_properties', {}))
            format_json = json.dumps(metadata.get('format_info', {}))
            
            cur.execute("""
                UPDATE file_hashes SET
                    vorbis_tags = ?,
                    audio_properties = ?,
                    format_info = ?,
                    has_artwork = ?,
                    artwork_count = ?,
                    metadata_scanned = 1
                WHERE file_path = ?
            """, (
                vorbis_json,
                audio_json,
                format_json,
                metadata.get('has_artwork', 0),
                metadata.get('artwork_count', 0),
                str(path)
            ))
    
    conn.commit()
    print(f"\nScanned {len(files_to_scan)} files")


def main():
    parser = argparse.ArgumentParser(
        description="Scan and store FLAC metadata in database"
    )
    parser.add_argument(
        "root",
        type=Path,
        nargs='?',
        help="Root directory to scan"
    )
    parser.add_argument(
        "--all-roots",
        action="store_true",
        help="Scan MUSIC, Quarantine, and Garbage"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Database path (default: {DB_PATH})"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of files to scan (0=all)"
    )
    
    args = parser.parse_args()
    
    if not args.db.exists():
        print(f"Database not found: {args.db}")
        print("Run scan_all_roots.py first to populate file hashes")
        return 1
    
    conn = sqlite3.connect(args.db, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Initialize metadata schema
    print("Initializing metadata schema...")
    init_metadata_schema(conn)
    
    # Determine roots to scan
    roots = []
    if args.all_roots:
        roots = [
            Path("/Volumes/dotad/MUSIC"),
            Path("/Volumes/dotad/Quarantine"),
            Path("/Volumes/dotad/Garbage"),
        ]
    elif args.root:
        roots = [args.root]
    else:
        print("Error: Specify a root directory or use --all-roots")
        return 1
    
    # Scan each root
    for root in roots:
        if not root.exists():
            print(f"Warning: Root not found: {root}")
            continue
        
        print(f"\n{'='*60}")
        print(f"Scanning: {root}")
        print(f"{'='*60}")
        
        scan_and_update_metadata(root, conn, args.limit)
    
    conn.close()
    print("\nMetadata scan complete!")
    
    return 0


if __name__ == "__main__":
    exit(main())
