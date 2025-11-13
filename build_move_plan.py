#!/usr/bin/env python3
"""Build intelligent move plan with health-based selection."""

import sqlite3
from pathlib import Path
from collections import defaultdict
import csv
from typing import Dict, List, Tuple

db = Path.home() / '.cache' / 'file_dupes.db'
conn = sqlite3.connect(db)
cur = conn.cursor()

music_root = Path('/Volumes/dotad/MUSIC')
quarantine_root = Path('/Volumes/dotad/Quarantine')
garbage_root = Path('/Volumes/dotad/Garbage')
new_library = Path('/Volumes/dotad/NEW_LIBRARY')

# Get all files
cur.execute('''
    SELECT file_md5, file_path, artist, album, title, bitrate, sample_rate
    FROM file_hashes
    ORDER BY file_md5, file_path
''')

by_md5: Dict[str, List] = defaultdict(list)
for md5, path, artist, album, title, br, sr in cur.fetchall():
    p = Path(path)
    if p.exists():
        by_md5[md5].append({
            'path': p,
            'artist': artist,
            'album': album,
            'title': title,
            'bitrate': br or 0,
            'sample_rate': sr or 0,
            'size': p.stat().st_size,
        })

def get_root_priority(path: Path) -> Tuple[int, str]:
    """Score path by source. Higher = better."""
    if music_root in path.parents or path == music_root:
        return (3, 'MUSIC')
    elif garbage_root in path.parents or path == garbage_root:
        return (2, 'Garbage')
    elif quarantine_root in path.parents or path == quarantine_root:
        return (1, 'Quarantine')
    return (0, 'Unknown')

def score_file(file_info: Dict) -> Tuple[int, int, int]:
    """Score file for selection. Higher = better."""
    path = file_info['path']
    priority, _ = get_root_priority(path)
    bitrate = file_info['bitrate'] or 0
    sample_rate = file_info['sample_rate'] or 0
    return (priority, bitrate, sample_rate)

# Build move plan
plan: List = []
for md5, files in by_md5.items():
    if not files:
        continue

    # Choose best file
    best = max(files, key=score_file)
    _, source_root = get_root_priority(best['path'])

    # Keep original path structure
    source_path = best['path']
    rel_path = source_path.relative_to(source_path.parents[-3])  # Strip root
    dest_path = new_library / rel_path

    plan.append({
        'md5': md5,
        'source': str(source_path),
        'destination': str(dest_path),
        'size': best['size'],
        'source_root': source_root,
        'bitrate': best['bitrate'] or 0,
        'sample_rate': best['sample_rate'] or 0,
    })

# Statistics
by_source: Dict[str, int] = defaultdict(int)
total_size = 0
for item in plan:
    by_source[item['source_root']] += 1
    total_size += item['size']

print(f'=== New Library Move Plan ===')
print(f'Total unique files: {len(plan)}')
print(f'Total size: {total_size / (1024**3):.2f} GiB')
print()
print('By source (priority):')
for source in ['MUSIC', 'Garbage', 'Quarantine', 'Unknown']:
    count = by_source[source]
    if count > 0:
        size = sum(p['size'] for p in plan if p['source_root'] == source)
        print(f'  {source:12} {count:6} files  ({size / (1024**3):7.2f} GiB)')

# Write plan
csv_path = Path('artifacts/reports/library_move_plan.csv')
csv_path.parent.mkdir(parents=True, exist_ok=True)

with csv_path.open('w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'md5', 'source', 'destination', 'size',
        'source_root', 'bitrate', 'sample_rate'
    ])
    writer.writeheader()
    writer.writerows(plan)

print(f'\nMove plan: {csv_path}')

# Recommended next steps
print(f'\n=== Recommended Strategy ===')
print(f'1. Create new library directory: mkdir -p {new_library}')
print(f'2. Review move plan: {csv_path}')
print(f'3. Run health checks on Quarantine files (9,019 files)')
print(f'4. Execute moves with: python scripts/execute_library_move.py --commit')
print(f'5. Verify all files moved: {new_library}')

conn.close()
