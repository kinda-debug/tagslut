#!/usr/bin/env python3
"""
M3U Playlist Cleanup

Scans /Volumes/MUSIC/MASTER_LIBRARY/playlists/ and renames M3U files
from garbage timestamps (roon-tidal-20260326-232119.m3u) to actual playlist names
extracted from the file content.

Deduplicates identical playlists (same track list, different names).
"""

import os
import re
import json
from pathlib import Path
from collections import defaultdict
import hashlib

PLAYLIST_DIR = Path("/Volumes/MUSIC/MASTER_LIBRARY/playlists")


def extract_playlist_name(m3u_path: Path) -> str | None:
    """
    Extract a meaningful playlist name from the M3U file.
    
    Tries:
    1. #PLAYLIST: tag value (if it's not a garbage timestamp)
    2. Album name extracted from file paths in the M3U
    3. Falls back to original filename
    """
    try:
        with open(m3u_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"ERROR reading {m3u_path}: {e}")
        return None
    
    # Try #PLAYLIST tag
    playlist_match = re.search(r'#PLAYLIST:(.+)', content)
    if playlist_match:
        playlist_name = playlist_match.group(1).strip()
        # Skip if it's clearly a timestamp
        if not re.match(r'^(roon-|tidal-|bpdl-|ingest-|beatport-|special_pool)', playlist_name) and len(playlist_name) > 15:
            return playlist_name
    
    # Try extracting album from file paths
    # Look for patterns like: Artist/Album/Track.flac or Artist/Album (Year)/Track.flac
    path_matches = re.findall(r'/([^/]+)/([^/]+\.flac|[^/]+\([0-9]+\)/[^/]+\.flac)', content)
    if path_matches:
        # Most common album in the list
        albums = defaultdict(int)
        for match in path_matches:
            # Extract album from the second path component
            if len(match) > 1:
                album_path = match[1]
                # Clean up year suffix
                album = re.sub(r'\s*\([0-9]+\)\s*', '', album_path).strip()
                if album and not album.startswith('['):
                    albums[album] += 1
        
        if albums:
            most_common_album = max(albums, key=albums.get)
            if most_common_album and len(most_common_album) > 5:
                return most_common_album
    
    return None


def get_playlist_hash(m3u_path: Path) -> str:
    """Get SHA256 of sorted track list (for deduplication)."""
    try:
        with open(m3u_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith('#')]
        sorted_tracks = sorted(lines)
        payload = '\n'.join(sorted_tracks)
        return hashlib.sha256(payload.encode()).hexdigest()
    except Exception:
        return hashlib.sha256(str(m3u_path).encode()).hexdigest()


def is_garbage_name(filename: str) -> bool:
    """Check if filename is a garbage timestamp."""
    return bool(re.match(r'^roon-(tidal|beatport|ingest|bpdl|special_pool)-', filename))


def main():
    """Main cleanup logic."""
    print(f"Scanning {PLAYLIST_DIR}...")
    
    # Group by hash to find duplicates
    hashes_to_files = defaultdict(list)
    meaningfully_named = []
    garbage_named = []
    
    for m3u_file in sorted(PLAYLIST_DIR.glob('*.m3u')):
        file_hash = get_playlist_hash(m3u_file)
        hashes_to_files[file_hash].append(m3u_file)
        
        if is_garbage_name(m3u_file.name):
            garbage_named.append(m3u_file)
        else:
            meaningfully_named.append(m3u_file)
    
    print(f"\nFound {len(meaningfully_named)} meaningfully-named playlists")
    print(f"Found {len(garbage_named)} garbage-named playlists")
    print(f"Total {len(list(PLAYLIST_DIR.glob('*.m3u')))} M3U files")
    
    # Plan renames
    renames = {}
    duplicates_to_delete = []
    
    for garbage_file in garbage_named:
        new_name = extract_playlist_name(garbage_file)
        if new_name:
            # Check for duplicate content
            file_hash = get_playlist_hash(garbage_file)
            similar_files = hashes_to_files[file_hash]
            
            # If there's already a meaningfully-named version, mark garbage for deletion
            has_meaningful_dup = any(not is_garbage_name(f.name) for f in similar_files)
            if has_meaningful_dup:
                duplicates_to_delete.append(garbage_file)
            else:
                # Propose rename
                new_path = PLAYLIST_DIR / f"roon-{new_name}.m3u"
                
                # Avoid collisions
                counter = 1
                base_name = new_name
                while new_path.exists():
                    new_name_with_num = f"{base_name} ({counter})"
                    new_path = PLAYLIST_DIR / f"roon-{new_name_with_num}.m3u"
                    counter += 1
                
                renames[garbage_file] = new_path
    
    # Display plan
    print(f"\n=== RENAME PLAN ===\n")
    for old, new in sorted(renames.items()):
        print(f"RENAME: {old.name}")
        print(f"     TO: {new.name}\n")
    
    print(f"=== DELETE PLAN (DUPLICATES) ===\n")
    for dup in duplicates_to_delete:
        print(f"DELETE: {dup.name} (duplicate of a meaningfully-named version)\n")
    
    # Ask for confirmation
    print(f"\nSummary:")
    print(f"  Renames: {len(renames)}")
    print(f"  Deletes: {len(duplicates_to_delete)}")
    print(f"  Meaningfully-named (keep): {len(meaningfully_named)}")
    
    response = input("\nProceed? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Aborted.")
        return
    
    # Execute renames
    for old, new in renames.items():
        try:
            old.rename(new)
            print(f"✓ Renamed {old.name} → {new.name}")
        except Exception as e:
            print(f"✗ Failed to rename {old.name}: {e}")
    
    # Execute deletes
    for dup in duplicates_to_delete:
        try:
            dup.unlink()
            print(f"✓ Deleted {dup.name} (duplicate)")
        except Exception as e:
            print(f"✗ Failed to delete {dup.name}: {e}")
    
    # Final summary
    remaining = list(PLAYLIST_DIR.glob('*.m3u'))
    print(f"\n=== FINAL STATE ===")
    print(f"Total M3U files remaining: {len(remaining)}")
    
    # Count by prefix
    prefixes = defaultdict(int)
    for m3u in remaining:
        prefix = m3u.name.split('-')[1].split('_')[0] if '-' in m3u.name else 'other'
        prefixes[prefix] += 1
    
    print(f"\nBreakdown:")
    for prefix, count in sorted(prefixes.items()):
        print(f"  roon-{prefix}: {count}")


if __name__ == '__main__':
    main()
