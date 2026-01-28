#!/usr/bin/env python3
"""
Analyze source-to-destination mapping for promote_by_tags.py:
- Count how many source files map to the same destination (duplicates)
- Count missing sources
- Count tag errors/corrupt files
- Output summary and optionally details

Usage:
    python analyze_promotion_sources.py kept.txt
"""
import sys
from pathlib import Path
from collections import defaultdict, Counter
from mutagen.flac import FLAC, FLACNoHeaderError
from mutagen import MutagenError

def build_destination(tags):
    # Dummy: replace with your actual build_destination logic
    # For demo, just use artist/album/title
    artist = tags.get('artist', ['Unknown Artist'])[0]
    album = tags.get('album', ['Unknown Album'])[0]
    title = tags.get('title', ['Unknown Title'])[0]
    return f"{artist}/{album}/{title}.flac"

def main(paths_file):
    with open(paths_file) as f:
        sources = [Path(line.strip()) for line in f if line.strip()]
    dest_map = defaultdict(list)
    missing = []
    corrupt = []
    for src in sources:
        if not src.exists():
            missing.append(str(src))
            continue
        try:
            tags = FLAC(src)
        except (FLACNoHeaderError, MutagenError, ValueError) as exc:
            corrupt.append(str(src))
            continue
        dest = build_destination(tags)
        dest_map[dest].append(str(src))
    # Count duplicates
    duplicate_groups = {k: v for k, v in dest_map.items() if len(v) > 1}
    print(f"Total sources: {len(sources)}")
    print(f"Missing: {len(missing)}")
    print(f"Corrupt/tag error: {len(corrupt)}")
    print(f"Unique destinations: {len(dest_map)}")
    print(f"Duplicate destination groups: {len(duplicate_groups)}")
    if duplicate_groups:
        print("\nSample duplicate group:")
        for dest, group in list(duplicate_groups.items())[:3]:
            print(f"Destination: {dest}")
            for src in group:
                print(f"  {src}")
    if missing:
        print("\nSample missing:")
        for m in missing[:3]:
            print(f"  {m}")
    if corrupt:
        print("\nSample corrupt:")
        for c in corrupt[:3]:
            print(f"  {c}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_promotion_sources.py kept.txt")
        sys.exit(1)
    main(sys.argv[1])
