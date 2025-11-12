#!/usr/bin/env python3
"""Verify JSON metadata storage is working correctly."""
import sqlite3
import json
from pathlib import Path

DB_PATH = Path.home() / ".cache" / "file_dupes.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=== Metadata Storage Verification ===\n")

# Check total files with metadata
cur.execute("SELECT COUNT(*) FROM file_hashes WHERE metadata_scanned = 1")
total_scanned = cur.fetchone()[0]
print(f"Total files scanned: {total_scanned}")

# Check JSON column population
cur.execute("""
    SELECT COUNT(*) FROM file_hashes 
    WHERE vorbis_tags IS NOT NULL
""")
with_vorbis = cur.fetchone()[0]

cur.execute("""
    SELECT COUNT(*) FROM file_hashes 
    WHERE audio_properties IS NOT NULL
""")
with_audio = cur.fetchone()[0]

print(f"Files with vorbis_tags: {with_vorbis}")
print(f"Files with audio_properties: {with_audio}")

# Show sample metadata from newly scanned files
print("\n=== Sample New JSON Metadata ===")
cur.execute("""
    SELECT file_path, vorbis_tags, audio_properties, 
           has_artwork, artwork_count
    FROM file_hashes
    WHERE metadata_scanned = 1
    AND vorbis_tags IS NOT NULL
    ORDER BY ROWID DESC
    LIMIT 3
""")

for idx, row in enumerate(cur.fetchall(), 1):
    path, vorbis_json, audio_json, has_artwork, artwork_count = row
    
    print(f"\n--- Sample {idx}: {Path(path).name} ---")
    
    if vorbis_json:
        tags = json.loads(vorbis_json)
        print(f"Vorbis tags ({len(tags)} keys):")
        for key in sorted(tags.keys())[:8]:  # Show first 8
            value = tags[key]
            if isinstance(value, str) and len(value) > 60:
                value = value[:60] + "..."
            print(f"  {key}: {value}")
        if len(tags) > 8:
            print(f"  ... and {len(tags) - 8} more tags")
    
    if audio_json:
        props = json.loads(audio_json)
        print(f"Audio properties ({len(props)} keys):")
        important = ['codec_name', 'sample_rate', 'channels', 
                     'bit_rate', 'duration']
        for key in important:
            if key in props:
                print(f"  {key}: {props[key]}")
    
    print(f"Artwork: {artwork_count} embedded picture(s)")

conn.close()
