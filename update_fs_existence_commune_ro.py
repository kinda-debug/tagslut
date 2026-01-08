#!/usr/bin/env python3
# Proves: read-only existence capture for /Volumes/COMMUNE prefixes and comparison vs prior fs_existence CSVs.
# Does not prove: filesystem correctness or provenance beyond CSV contents.

import csv
import os
import hashlib
from pathlib import Path

base = Path('/Users/georgeskhawam/Projects/dedupe')

prefixes = [
    '/Volumes/COMMUNE/R2',
    '/Volumes/COMMUNE/Root',
    '/Volumes/COMMUNE/_PROMOTION_STAGING',
]

new_files = {}
comparison_rows = []

for prefix in prefixes:
    sanitized = prefix.lstrip('/').replace('/', '__')
    old_path = base / f'fs_existence_{sanitized}.csv'
    new_path = base / f'fs_existence_ro_{sanitized}.csv'

    if not old_path.exists():
        raise SystemExit(f'Missing expected input: {old_path}')

    paths = []
    with old_path.open(newline='') as f:
        reader = csv.DictReader(f)
        if 'path' not in reader.fieldnames:
            raise SystemExit(f'Missing path column in {old_path}')
        for row in reader:
            paths.append(row['path'])

    paths = sorted(set(paths))

    with new_path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['path', 'exists', 'size', 'mtime'])
        for path in paths:
            exists = 1 if os.path.exists(path) else 0
            size = None
            mtime = None
            if exists:
                try:
                    st = os.stat(path)
                    size = st.st_size
                    mtime = st.st_mtime
                except OSError:
                    size = None
                    mtime = None
            writer.writerow([path, exists, size, mtime])

    # comparison stats
    def load_exists(p: Path) -> dict:
        data = {}
        with p.open(newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row.get('path')
                if key is None:
                    continue
                data[key] = 1 if row.get('exists') == '1' else 0
        return data

    old_map = load_exists(old_path)
    new_map = load_exists(new_path)

    all_paths = set(old_map) | set(new_map)
    old_present = sum(old_map.values())
    old_missing = len(old_map) - old_present
    new_present = sum(new_map.values())
    new_missing = len(new_map) - new_present

    changed_to_present = 0
    changed_to_missing = 0
    only_in_old = 0
    only_in_new = 0

    for path in all_paths:
        old_val = old_map.get(path)
        new_val = new_map.get(path)
        if old_val is None:
            only_in_new += 1
            continue
        if new_val is None:
            only_in_old += 1
            continue
        if old_val == 0 and new_val == 1:
            changed_to_present += 1
        elif old_val == 1 and new_val == 0:
            changed_to_missing += 1

    comparison_rows.append([
        prefix,
        len(all_paths),
        old_present,
        old_missing,
        new_present,
        new_missing,
        changed_to_present,
        changed_to_missing,
        only_in_old,
        only_in_new,
    ])

    new_files[prefix] = new_path

# Write comparison file
comparison_path = base / 'fs_existence_commune_comparison.csv'
with comparison_path.open('w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow([
        'prefix',
        'total_paths',
        'old_present',
        'old_missing',
        'new_present',
        'new_missing',
        'changed_to_present',
        'changed_to_missing',
        'paths_only_in_old',
        'paths_only_in_new',
    ])
    for row in sorted(comparison_rows, key=lambda x: x[0]):
        writer.writerow(row)

# Build summary using ro_bad + ro_commune + existing others
summary_path = base / 'fs_existence_summary_by_prefix_ro_bad_commune.csv'

prefix_to_file = {}
for path in base.glob('fs_existence_*.csv'):
    if path.name == 'fs_existence_paths_to_prepare.csv':
        continue
    name = path.stem[len('fs_existence_'):]
    prefix = '/' + name.replace('__', '/')
    if prefix.startswith('/Volumes/bad') or prefix.startswith('/Volumes/COMMUNE'):
        continue
    prefix_to_file[prefix] = path

# Add ro_bad files
for prefix in [
    '/Volumes/bad/.dedupe_db',
    '/Volumes/bad/FINAL_LIBRARY',
    '/Volumes/bad/_ALL_FLACS_FLAT',
    '/Volumes/bad/_BAD_VS_DOTAD_DISCARDS',
]:
    sanitized = prefix.lstrip('/').replace('/', '__')
    prefix_to_file[prefix] = base / f'fs_existence_ro_{sanitized}.csv'

# Add ro_commune files
for prefix, path in new_files.items():
    prefix_to_file[prefix] = path

rows = []
for prefix, path in prefix_to_file.items():
    total = 0
    present = 0
    missing = 0
    with path.open(newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            if row.get('exists') == '1':
                present += 1
            else:
                missing += 1
    rows.append((prefix, total, missing, present, str(path)))

with summary_path.open('w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['prefix', 'total_rows', 'missing_paths', 'present_paths', 'source_file'])
    for row in sorted(rows, key=lambda x: x[0]):
        writer.writerow(row)

# Print outputs with row counts and sha256
outputs = list(new_files.values()) + [comparison_path, summary_path]

for path in outputs:
    with path.open(newline='') as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    print(f"{path}\t{row_count}\t{h.hexdigest()}")
