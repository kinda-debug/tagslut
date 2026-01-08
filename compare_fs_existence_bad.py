#!/usr/bin/env python3
# Proves: compares old vs read-only /Volumes/bad fs_existence CSVs and quantifies changes by prefix.
# Does not prove: filesystem correctness, file identity, or any provenance beyond CSV contents.

import csv
import hashlib
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")

PREFIXES = [
    "/Volumes/bad/.dedupe_db",
    "/Volumes/bad/FINAL_LIBRARY",
    "/Volumes/bad/_ALL_FLACS_FLAT",
    "/Volumes/bad/_BAD_VS_DOTAD_DISCARDS",
]

OUT = BASE / "fs_existence_bad_comparison.csv"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_exists_map(path: Path) -> dict:
    data = {}
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            p = row.get("path")
            if p is None:
                continue
            data[p] = 1 if row.get("exists") == "1" else 0
    return data


rows = []
for prefix in PREFIXES:
    sanitized = prefix.lstrip("/").replace("/", "__")
    old_path = BASE / f"fs_existence_{sanitized}.csv"
    new_path = BASE / f"fs_existence_ro_{sanitized}.csv"

    if not old_path.exists() or not new_path.exists():
        raise SystemExit(f"Missing expected files for {prefix}: {old_path}, {new_path}")

    old_map = load_exists_map(old_path)
    new_map = load_exists_map(new_path)

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

    rows.append([
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

with OUT.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "prefix",
        "total_paths",
        "old_present",
        "old_missing",
        "new_present",
        "new_missing",
        "changed_to_present",
        "changed_to_missing",
        "paths_only_in_old",
        "paths_only_in_new",
    ])
    for row in sorted(rows, key=lambda x: x[0]):
        writer.writerow(row)

with OUT.open(newline="") as f:
    row_count = sum(1 for _ in csv.reader(f)) - 1

print(f"{OUT}\t{row_count}\t{sha256_path(OUT)}")
