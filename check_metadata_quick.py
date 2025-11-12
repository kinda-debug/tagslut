#!/usr/bin/env python3
"""Quick analysis - no scanning, just query existing data."""
import sqlite3
import json
from pathlib import Path

conn = sqlite3.connect(Path.home() / ".cache" / "file_dupes.db")
cur = conn.cursor()

# Count scanned
cur.execute("SELECT COUNT(*) FROM file_hashes WHERE metadata_scanned = 1")
scanned = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM file_hashes")
total = cur.fetchone()[0]

print(f"Metadata scanned: {scanned:,} / {total:,} files ({scanned/total*100:.1f}%)\n")

# Sample 3 files with metadata
cur.execute("""
    SELECT file_path, vorbis_tags, audio_properties, artwork_count
    FROM file_hashes
    WHERE metadata_scanned = 1 
    AND vorbis_tags IS NOT NULL
    LIMIT 3
""")

print("="*70)
print("SAMPLE METADATA (3 random files)")
print("="*70)

for path, vorbis_json, audio_json, art_count in cur.fetchall():
    name = Path(path).name
    vorbis = json.loads(vorbis_json) if vorbis_json else {}
    audio = json.loads(audio_json) if audio_json else {}
    
    print(f"\n{name}")
    print(f"  Tags: {len(vorbis)} fields")
    print(f"  Artwork: {art_count or 0} picture(s)")
    
    if audio.get('bit_rate'):
        br = int(audio['bit_rate']) / 1000  # to kbps
        print(f"  Bitrate: {br:.0f} kbps")
    
    # Show sample tags
    for key in ['ARTIST', 'ALBUM', 'DATE']:
        if key in vorbis:
            val = vorbis[key]
            if isinstance(val, list):
                val = val[0]
            print(f"  {key}: {val}")

conn.close()
