#!/usr/bin/env python3
"""
Compare audio quality between Garbage copy and NEW_LIBRARY selections.
Uses ffprobe to extract bitrate and sample rate.
"""
import subprocess
import os
import random
from pathlib import Path

def get_audio_info(filepath):
    """Extract bitrate and sample rate using ffprobe."""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=bit_rate,sample_rate',
            '-of', 'default=noprint_wrappers=1:nokey=1:nk=1',
            filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                bitrate = int(lines[0]) // 1000 if lines[0].isdigit() else 0  # Convert to kbps
                sample_rate = int(lines[1]) if lines[1].isdigit() else 0  # Hz
                return bitrate, sample_rate
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return 0, 0

def find_matching_file(garbage_path, new_library_base):
    """Find the corresponding file in NEW_LIBRARY by filename."""
    filename = os.path.basename(garbage_path)
    
    # Search in NEW_LIBRARY
    for root, dirs, files in os.walk(new_library_base):
        if filename in files:
            return os.path.join(root, filename)
    return None

def main():
    garbage_copy = Path('/Volumes/dotad/Garbage copy')
    new_library = Path('/Volumes/dotad/NEW_LIBRARY')
    
    if not garbage_copy.exists():
        print("❌ Garbage copy not found")
        return
    
    if not new_library.exists():
        print("❌ NEW_LIBRARY not found")
        return
    
    print("=" * 100)
    print("AUDIO QUALITY COMPARISON: Garbage Copy vs NEW_LIBRARY")
    print("=" * 100)
    
    # Find all FLAC files in Garbage copy
    garbage_files = list(garbage_copy.rglob('*.flac'))
    print(f"\nFound {len(garbage_files)} FLAC files in Garbage copy")
    
    if len(garbage_files) == 0:
        print("No FLAC files found to compare")
        return
    
    # Sample 10 random files
    samples = random.sample(garbage_files, min(10, len(garbage_files)))
    
    results = []
    
    for i, garbage_file in enumerate(samples, 1):
        filename = garbage_file.name
        
        # Find corresponding file in NEW_LIBRARY
        new_lib_file = find_matching_file(garbage_file, new_library)
        
        if not new_lib_file:
            print(f"\n[{i}] ❌ {filename}")
            print(f"    NOT FOUND in NEW_LIBRARY (may have been deleted)")
            continue
        
        # Get audio info for both files
        print(f"\n[{i}] {filename}")
        
        garbage_bitrate, garbage_sr = get_audio_info(str(garbage_file))
        new_bitrate, new_sr = get_audio_info(new_lib_file)
        
        if garbage_bitrate == 0:
            print(f"    Could not read Garbage copy metadata")
        else:
            print(f"    Garbage copy:  {garbage_bitrate} kbps, {garbage_sr} Hz")
        
        if new_bitrate == 0:
            print(f"    Could not read NEW_LIBRARY metadata")
        else:
            print(f"    NEW_LIBRARY:   {new_bitrate} kbps, {new_sr} Hz")
        
        # Compare
        if garbage_bitrate > 0 and new_bitrate > 0:
            if garbage_bitrate > new_bitrate:
                diff = garbage_bitrate - new_bitrate
                print(f"    ⚠️  GARBAGE COPY IS HIGHER: +{diff} kbps")
                results.append(('better_in_garbage', filename, diff))
            elif new_bitrate > garbage_bitrate:
                diff = new_bitrate - garbage_bitrate
                print(f"    ✓ NEW_LIBRARY IS HIGHER: +{diff} kbps")
                results.append(('better_in_new_library', filename, diff))
            else:
                print(f"    = SAME QUALITY")
                results.append(('equal', filename, 0))
    
    # Summary
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    
    better_in_garbage = [r for r in results if r[0] == 'better_in_garbage']
    better_in_new = [r for r in results if r[0] == 'better_in_new_library']
    equal = [r for r in results if r[0] == 'equal']
    
    print(f"\n✓ NEW_LIBRARY is better or equal: {len(better_in_new) + len(equal)} files")
    print(f"⚠️  Garbage copy is better: {len(better_in_garbage)} files")
    
    if better_in_garbage:
        print("\nFiles where Garbage copy has HIGHER quality:")
        for _, filename, diff in sorted(better_in_garbage, key=lambda x: x[2], reverse=True):
            print(f"  +{diff} kbps: {filename}")
    
    if better_in_new or equal:
        print("\nFiles where NEW_LIBRARY is same or better:")
        count = len(better_in_new) + len(equal)
        print(f"  {count} files are equivalent or improved")
    
    print("\n" + "=" * 100)
    if len(better_in_garbage) > len(better_in_new) // 2:
        print("⚠️  RECOMMENDATION: Consider restoring from Garbage copy")
        print("   A significant portion of files have higher bitrate in the original")
    else:
        print("✓ RECOMMENDATION: NEW_LIBRARY selection appears sound")
        print("  Most files are same quality or better in the consolidated library")
    print("=" * 100)

if __name__ == '__main__':
    main()
