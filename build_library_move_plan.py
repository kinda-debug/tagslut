#!/usr/bin/env python3
"""Build plan to move healthiest unique files to new Library."""

import sqlite3
from pathlib import Path
from collections import defaultdict
import csv

db = Path.home() / '.cache' / 'file_dupes.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

music_root = Path('/Volumes/dotad/MUSIC')
quarantine_root = Path('/Volumes/dotad/Quarantine')
garbage_root = Path('/Volumes/dotad/Garbage')
new_library = Path('/Volumes/dotad/NEW_LIBRARY')

# Get all files grouped by MD5
cur.execute('''
    SELECT file_md5, file_path, artist, album, title
    FROM file_hashes
    ORDER BY file_md5, file_path
''')

by_md5 = defaultdict(list)
for md5, path, artist, album, title in cur.fetchall():
    p = Path(path)
    # Check if file still exists
    if p.exists():
        by_md5[md5].append({
            'path': p,
            'artist': artist,
            'album': album,
            'title': title,
            'size': p.stat().st_size if p.exists() else 0,
        })

# Function to score file by source (prefer MUSIC > Garbage > Quarantine)
def score_path(file_info):
    path = file_info['path']
    # Higher score = better choice
    if music_root in path.parents or path == music_root:
        return (3, str(path))  # MUSIC gets highest score
    elif quarantine_root in path.parents or path == quarantine_root:
        return (1, str(path))  # Quarantine gets lowest
    elif garbage_root in path.parents or path == garbage_root:
        return (2, str(path))  # Garbage is middle
    else:
        return (0, str(path))  # Unknown root

# Build move plan
plan = []
for md5, files in by_md5.items():
    if not files:
        continue

    # Choose best file (prefer MUSIC, then Garbage, then Quarantine)
    best = max(files, key=score_path)
    source_path = best['path']

    # Determine destination in new library
    # Try to preserve artist/album structure if metadata exists
    if best['artist'] and best['album']:
        rel_path = Path(best['artist']) / best['album'] / source_path.name
    elif best['artist']:
        rel_path = Path(best['artist']) / source_path.name
    else:
        rel_path = source_path.relative_to(source_path.parents[-2])

    dest_path = new_library / rel_path

    # Log other files that won't be moved
    other_files = [f for f in files if f['path'] != source_path]

    plan.append({
        'md5': md5,
        'source': str(source_path),
        'destination': str(dest_path),
        'size': best['size'],
        'artist': best['artist'] or '',
        'album': best['album'] or '',
        'title': best['title'] or '',
        'source_root': (
            'MUSIC' if music_root in source_path.parents or source_path == music_root
            else 'Quarantine' if quarantine_root in source_path.parents or source_path == quarantine_root
            else 'Garbage' if garbage_root in source_path.parents or source_path == garbage_root
            else 'Unknown'
        ),
        'abandoned_files': len(other_files),
        'abandoned_details': [str(f['path']) for f in other_files],
    })

print(f'Total unique MD5 groups: {len(plan)}')
print(f'Total files to move: {len(plan)}')
print(f'Total space: {sum(p["size"] for p in plan) / (1024**3):.2f} GiB')

# Show breakdown by source
by_source = defaultdict(int)
for item in plan:
    by_source[item['source_root']] += 1

print('\nBreakdown by source:')
for source, count in sorted(by_source.items()):
    print(f'  {source:12} {count:5} files')

# Write CSV plan
csv_path = Path('artifacts/reports/new_library_move_plan.csv')
csv_path.parent.mkdir(parents=True, exist_ok=True)

with csv_path.open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'md5', 'source', 'destination', 'size', 'artist', 'album',
        'title', 'source_root', 'abandoned_files'
    ])
    writer.writeheader()
    for item in plan:
        writer.writerow({
            'md5': item['md5'],
            'source': item['source'],
            'destination': item['destination'],
            'size': item['size'],
            'artist': item['artist'],
            'album': item['album'],
            'title': item['title'],
            'source_root': item['source_root'],
            'abandoned_files': item['abandoned_files'],
        })

print(f'\nMove plan saved to: {csv_path}')

conn.close()
