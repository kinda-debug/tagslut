#!/usr/bin/env python3
"""Check actual duplicates still on disk."""

import sqlite3
from pathlib import Path

db = Path.home() / '.cache' / 'file_dupes.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

garbage = '/Volumes/dotad/Garbage'

# Get all MD5 duplicates
cur.execute('''
    SELECT file_md5, file_path FROM file_hashes
    WHERE file_path LIKE ? OR file_path LIKE ? OR file_path LIKE ?
    ORDER BY file_md5
''', (f'{garbage}/%', '/Volumes/dotad/MUSIC/%',
      '/Volumes/dotad/Quarantine/%'))

by_md5 = {}
for md5, path in cur.fetchall():
    if md5 not in by_md5:
        by_md5[md5] = []
    by_md5[md5].append(path)

# Find actual duplicates (2+ existing files)
actual_dupes = {}
for md5, paths in by_md5.items():
    existing = [p for p in paths if Path(p).exists()]
    if len(existing) > 1:
        actual_dupes[md5] = existing

print(f'Actual duplicate groups: {len(actual_dupes)}')
print(f'Total duplicate files: {sum(len(p) for p in actual_dupes.values())}')

if actual_dupes:
    print('\nFirst 10 groups:')
    for i, (md5, paths) in enumerate(list(actual_dupes.items())[:10], 1):
        print(f'\n{i}. MD5: {md5[:8]}...')
        for path in paths:
            if 'Garbage' in path:
                marker = '[GARBAGE]'
            elif 'Quarantine' in path:
                marker = '[QUARAN]'
            else:
                marker = '[MUSIC]'
            print(f'   {marker} {Path(path).name}')

conn.close()
