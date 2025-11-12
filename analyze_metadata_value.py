#!/usr/bin/env python3
"""Analyze if metadata helps with filename duplicates - QUERY ONLY."""
import sqlite3
import json
from pathlib import Path
from collections import defaultdict

conn = sqlite3.connect(Path.home() / ".cache" / "file_dupes.db")
cur = conn.cursor()

print("Analyzing filename duplicates with metadata...\n")

# Get all scanned files
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

# Find filename dupes with DIFFERENT MD5 (different content)
dupes_diff_content = []
for name, files in by_name.items():
    if len(files) > 1:
        md5s = {f['md5'] for f in files}
        if len(md5s) > 1:
            dupes_diff_content.append((name, files))

print(f"Files scanned with metadata: {len(by_name):,}")
print(f"Filename duplicates found: {len(dupes_diff_content):,}\n")

if len(dupes_diff_content) == 0:
    print("No filename duplicates with different content in scanned set.")
    print("Metadata may not be needed - shortest path policy is fine.")
    conn.close()
    exit(0)

# Analyze metadata differences
print("="*70)
print("METADATA VALUE ANALYSIS")
print("="*70)

has_artwork_diff = 0
has_tag_diff = 0
has_bitrate_diff = 0

for name, files in dupes_diff_content:
    # Check artwork
    artworks = {f['artwork'] for f in files}
    if len(artworks) > 1:
        has_artwork_diff += 1
    
    # Check tag completeness
    tag_counts = {len(f['vorbis']) for f in files}
    if len(tag_counts) > 1:
        has_tag_diff += 1
    
    # Check bitrate
    bitrates = set()
    for f in files:
        br = f['audio'].get('bit_rate')
        if br:
            bitrates.add(int(br))
    if len(bitrates) > 1:
        has_bitrate_diff += 1

print(f"\nOut of {len(dupes_diff_content)} filename duplicate groups:")
print(f"  {has_artwork_diff} have different artwork counts")
print(f"  {has_tag_diff} have different tag completeness")
print(f"  {has_bitrate_diff} have different bitrates")

# Show examples
print("\n" + "="*70)
print("TOP 3 EXAMPLES")
print("="*70)

for idx, (name, files) in enumerate(dupes_diff_content[:3], 1):
    print(f"\n{idx}. {name}")
    print(f"   {len(files)} versions:")
    
    for i, f in enumerate(files, 1):
        root = Path(f['path']).parts[3]  # MUSIC/Quarantine/Garbage
        short_path = f"{root}/.../{Path(f['path']).name}"
        
        print(f"\n   v{i} ({short_path[:60]}...)")
        print(f"      MD5: {f['md5'][:12]}...")
        print(f"      Artwork: {f['artwork']} pic(s)")
        print(f"      Tags: {len(f['vorbis'])} fields")
        
        br = f['audio'].get('bit_rate')
        if br:
            print(f"      Bitrate: {int(br)/1000:.0f} kbps")

# Recommendation
print("\n" + "="*70)
print("RECOMMENDATION")
print("="*70)

total_with_diffs = has_artwork_diff + has_tag_diff + has_bitrate_diff
pct_useful = (total_with_diffs / len(dupes_diff_content) * 100) if dupes_diff_content else 0

if pct_useful > 30:
    print(f"\n✅ {pct_useful:.0f}% of filename dupes have meaningful quality differences")
    print("   Metadata IS valuable - continue scan to compare all duplicates")
    print("\n   Run: nohup python3 scripts/scan_metadata.py --all-roots &")
else:
    print(f"\n⚠️  Only {pct_useful:.0f}% of filename dupes have quality differences")
    print("   Metadata may not matter - shortest path policy is likely fine")
    print("\n   Consider: Just delete by shortest path without metadata")

conn.close()
