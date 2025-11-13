#!/usr/bin/env python3
"""
Compare FLAC files between Garbage copy and NEW_LIBRARY using flac command.
"""
import subprocess
import os
import random
from pathlib import Path

def get_flac_info(filepath):
    """Extract FLAC metadata using flac command."""
    try:
        result = subprocess.run(
            ['flac', '--show-md5sum', '--show-min-blocksize', 
             '--show-max-blocksize', '--show-min-framesize',
             '--show-max-framesize', '--show-bps', '--show-sample-rate',
             '--show-channels', filepath],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            # Parse output
            info = {}
            for line in lines:
                if '=' in line:
                    key, val = line.split('=', 1)
                    info[key.strip()] = val.strip()
            return info
    except Exception as e:
        pass
    return None

def find_matching_file(garbage_path, new_library_base):
    """Find the corresponding file in NEW_LIBRARY by filename."""
    filename = os.path.basename(garbage_path)
    for root, dirs, files in os.walk(new_library_base):
        if filename in files:
            return os.path.join(root, filename)
    return None

def main():
    garbage_copy = Path('/Volumes/dotad/Garbage copy')
    new_library = Path('/Volumes/dotad/NEW_LIBRARY')
    
    if not garbage_copy.exists():
        print("Garbage copy not found")
        return
    
    if not new_library.exists():
        print("NEW_LIBRARY not found")
        return
    
    print("=" * 100)
    print("AUDIO QUALITY COMPARISON: Garbage Copy vs NEW_LIBRARY")
    print("=" * 100)
    
    # Find all FLAC files in Garbage copy
    garbage_files = list(garbage_copy.rglob('*.flac'))
    print(f"\nFound {len(garbage_files)} FLAC files in Garbage copy")
    
    if len(garbage_files) == 0:
        print("No FLAC files found")
        return
    
    # Sample 10 random files
    samples = random.sample(garbage_files, min(10, len(garbage_files)))
    
    better_garbage = 0
    better_new = 0
    equal = 0
    
    for i, garbage_file in enumerate(samples, 1):
        filename = garbage_file.name
        
        # Find matching file in NEW_LIBRARY
        new_lib_file = find_matching_file(garbage_file, new_library)
        
        print(f"\n[{i}] {filename}")
        
        garbage_info = get_flac_info(str(garbage_file))
        new_info = get_flac_info(new_lib_file) if new_lib_file else None
        
        if garbage_info:
            sr = garbage_info.get('sample_rate', '?')
            ch = garbage_info.get('channels', '?')
            bps = garbage_info.get('bits_per_sample', '?')
            print(f"    Garbage:     {sr} Hz, {ch}ch, {bps}-bit")
        else:
            print(f"    Garbage:     [Could not read]")
        
        if new_info:
            sr = new_info.get('sample_rate', '?')
            ch = new_info.get('channels', '?')
            bps = new_info.get('bits_per_sample', '?')
            print(f"    NEW_LIBRARY: {sr} Hz, {ch}ch, {bps}-bit")
        else:
            if new_lib_file:
                print(f"    NEW_LIBRARY: [Could not read]")
            else:
                print(f"    NEW_LIBRARY: [FILE NOT FOUND - deleted!]")
        
        # Simple comparison
        if garbage_info and new_info:
            g_quality = (
                int(garbage_info.get('sample_rate', '0')) * 
                int(garbage_info.get('bits_per_sample', '0'))
            )
            n_quality = (
                int(new_info.get('sample_rate', '0')) * 
                int(new_info.get('bits_per_sample', '0'))
            )
            
            if g_quality > n_quality:
                print(f"    ⚠️  GARBAGE IS BETTER")
                better_garbage += 1
            elif n_quality > g_quality:
                print(f"    ✓ NEW_LIBRARY IS BETTER")
                better_new += 1
            else:
                print(f"    = EQUAL QUALITY")
                equal += 1
    
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    total = len(samples)
    print(f"\n✓ NEW_LIBRARY better or equal: {better_new + equal}/{total}")
    print(f"⚠️  Garbage copy better: {better_garbage}/{total}")
    
    if better_garbage > total // 2:
        print("\n⚠️  RECOMMENDATION: Consider restoring from Garbage copy")
    else:
        print("\n✓ RECOMMENDATION: NEW_LIBRARY selection appears sound")

if __name__ == '__main__':
    main()
