#!/usr/bin/env python3
"""Check for remaining duplicates across the three roots."""

import sqlite3
from pathlib import Path
from collections import defaultdict

db = Path.home() / '.cache' / 'file_dupes.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

music = '/Volumes/dotad/MUSIC'
quarantine = '/Volumes/dotad/Quarantine'
garbage = '/Volumes/dotad/Garbage'

# Get all files in the three roots
cur.execute('''
    SELECT file_md5, file_path FROM file_hashes 
    WHERE file_path LIKE ? OR file_path LIKE ? OR file_path LIKE ?
    ORDER BY file_md5
''', (f'{music}/%', f'{quarantine}/%', f'{garbage}/%'))

by_md5 = defaultdict(list)
for md5, path in cur.fetchall():
    by_md5[md5].append(path)

# Count duplicates
dupes = {md5: paths for md5, paths in by_md5.items() if len(paths) > 1}

print(f'Total unique files in 3 roots: {len(by_md5)}')
print(f'Duplicate MD5 groups: {len(dupes)}')
print(f'Total files in duplicate groups: {sum(len(paths) for paths in dupes.values())}')

# Check which still exist on disk
missing_count = 0
for md5, paths in dupes.items():
    for path in paths:
        if not Path(path).exists():
            missing_count += 1

print(f'Missing from disk: {missing_count}')

# Show detailed breakdown by root
print('\nBreakdown by root:')
for root, name in [(music, 'MUSIC'), (quarantine, 'Quarantine'), (garbage, 'Garbage')]:
    cur.execute('SELECT COUNT(*) FROM file_hashes WHERE file_path LIKE ?', (f'{root}/%',))
    count = cur.fetchone()[0]
    
    cur.execute('''
        SELECT COUNT(*) FROM file_hashes 
        WHERE file_path LIKE ? 
        AND file_md5 IN (SELECT file_md5 FROM file_hashes GROUP BY file_md5 HAVING COUNT(*) > 1)
    ''', (f'{root}/%',))
    dup_count = cur.fetchone()[0]
    
    print(f'  {name:12} {count:5} files,  {dup_count:3} in duplicate groups')

conn.close()
