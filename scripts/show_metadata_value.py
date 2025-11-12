#!/usr/bin/env python3
"""Show sample metadata value from scanned files."""
import sqlite3
import json
from pathlib import Path
from collections import defaultdict

DB_PATH = Path.home() / ".cache" / "file_dupes.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=== Metadata Scan Progress ===\n")

# Total scanned
cur.execute("SELECT COUNT(*) FROM file_hashes WHERE metadata_scanned = 1")
scanned = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM file_hashes")
total = cur.fetchone()[0]

print(f"Files scanned: {scanned:,} / {total:,} ({scanned/total*100:.1f}%)")

# Get filename duplicates that have metadata
cur.execute("""
    SELECT file_path, file_md5, file_size, vorbis_tags, 
           audio_properties, artwork_count
    FROM file_hashes
    WHERE metadata_scanned = 1
""")

# Group by basename
by_name = defaultdict(list)
for row in cur.fetchall():
    path, md5, size, vorbis_json, audio_json, art_count = row
    name = Path(path).name
    
    vorbis = json.loads(vorbis_json) if vorbis_json else {}
    audio = json.loads(audio_json) if audio_json else {}
    
    by_name[name].append({
        'path': path,
        'md5': md5,
        'size': size,
        'vorbis': vorbis,
        'audio': audio,
        'artwork': art_count or 0
    })

# Find filename dupes with different metadata
dupes_with_diff_metadata = []
for name, files in by_name.items():
    if len(files) > 1:
        # Check if MD5s differ
        md5s = {f['md5'] for f in files}
        if len(md5s) > 1:
            dupes_with_diff_metadata.append((name, files))

print(f"\nFilename duplicates found in scanned set: {len(dupes_with_diff_metadata)}")
print("\n" + "="*70)
print("SAMPLE: Filename Duplicates with Different Metadata")
print("="*70)

# Show top 5 examples
for idx, (name, files) in enumerate(dupes_with_diff_metadata[:5], 1):
    print(f"\n--- Example {idx}: {name} ---")
    print(f"Versions: {len(files)}")
    
    for i, f in enumerate(files, 1):
        print(f"\n  Version {i}:")
        print(f"    Path: {f['path']}")
        print(f"    MD5: {f['md5'][:16]}...")
        print(f"    Size: {f['size']:,} bytes")
        print(f"    Artwork: {f['artwork']} picture(s)")
        
        # Show key tags
        v = f['vorbis']
        if v:
            print(f"    Tags: {len(v)} fields")
            for key in ['ARTIST', 'ALBUM', 'TITLE', 'DATE'][:3]:
                if key in v:
                    val = v[key]
                    if isinstance(val, list):
                        val = val[0]
                    if len(str(val)) > 50:
                        val = str(val)[:50] + "..."
                    print(f"      {key}: {val}")
        
        # Show audio quality
        a = f['audio']
        if a:
            br = a.get('bit_rate', 'unknown')
            sr = a.get('sample_rate', 'unknown')
            print(f"    Audio: {br} bps, {sr} Hz")

# Show value analysis
print("\n" + "="*70)
print("METADATA VALUE ANALYSIS")
print("="*70)

if len(dupes_with_diff_metadata) > 0:
    example_name, example_files = dupes_with_diff_metadata[0]
    
    print(f"\nUsing '{example_name}' as example:")
    print("\nWhat metadata reveals:")
    
    differences = []
    
    # Check artwork differences
    artworks = [f['artwork'] for f in example_files]
    if len(set(artworks)) > 1:
        differences.append(f"  • Artwork: {artworks[0]} vs {artworks[1]} embedded pictures")
    
    # Check tag completeness
    tag_counts = [len(f['vorbis']) for f in example_files]
    if len(set(tag_counts)) > 1:
        differences.append(f"  • Tag completeness: {tag_counts[0]} vs {tag_counts[1]} fields")
    
    # Check bitrate
    bitrates = []
    for f in example_files:
        br = f['audio'].get('bit_rate')
        if br:
            bitrates.append(int(br))
    if len(set(bitrates)) > 1:
        differences.append(f"  • Bitrate: {bitrates[0]:,} vs {bitrates[1]:,} bps")
    
    if differences:
        print("\n".join(differences))
        print("\n✅ METADATA HELPS: Can choose better quality version!")
    else:
        print("  • Files appear identical in quality")
        print("\n⚠️  Metadata may not help - shortest path is fine")

print("\n" + "="*70)
print("RECOMMENDATION")
print("="*70)

if len(dupes_with_diff_metadata) >= 3:
    print(f"\n✅ Found {len(dupes_with_diff_metadata)} filename dupes with different metadata")
    print("   in just the scanned subset.")
    print("\n   Metadata scan IS valuable for choosing better versions.")
    print("   Continue scan or run overnight with nohup.")
else:
    print("\n⚠️  Very few filename dupes with metadata differences found.")
    print("   Most duplicates may be identical except for path.")
    print("   Consider shortest-path policy without metadata.")

conn.close()
