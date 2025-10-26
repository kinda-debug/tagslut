#!/usr/bin/env python3
"""
Create an M3U playlist from the paths in _BROKEN_FILES.txt.
Usage: python3 make_broken_playlist.py /Volumes/dotad/MUSIC/_BROKEN_FILES.txt /Volumes/dotad/MUSIC/broken_files.m3u
"""
import sys

if len(sys.argv) != 3:
    print("Usage: python3 make_broken_playlist.py <input_txt> <output_m3u>")
    sys.exit(1)

input_txt = sys.argv[1]
output_m3u = sys.argv[2]

with open(input_txt, 'r') as fin, open(output_m3u, 'w') as fout:
    for line in fin:
        parts = line.strip().split('\t')
        if len(parts) >= 2:
            path = parts[1]
            fout.write(f"{path}\n")

print(f"Playlist written to {output_m3u}")
