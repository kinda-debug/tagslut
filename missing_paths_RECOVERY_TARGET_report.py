#!/usr/bin/env python3
# Proves: lists DB paths under /Volumes/RECOVERY_TARGET/Root that are marked missing in fs_existence CSV, with their DB checksums,
#         scan-run first/last timestamps (if present in file_scan_runs), and checksum matches in other prefixes found in attached DBs.
# Does not prove: filesystem existence, checksum correctness, file identity, or that any match implies a safe merge/deduplication.

import csv
import hashlib
import sqlite3
from pathlib import Path

PREFIX = "/Volumes/RECOVERY_TARGET/Root"
FS_EXISTENCE = Path("/Users/georgeskhawam/Projects/dedupe/fs_existence_Volumes__RECOVERY_TARGET__Root.csv")
OUT_MAIN = Path("/Users/georgeskhawam/Projects/dedupe/missing_paths_RECOVERY_TARGET_checksum_matches.csv")
OUT_SUMMARY = Path("/Users/georgeskhawam/Projects/dedupe/missing_paths_RECOVERY_TARGET_checksum_twin_summary.csv")

DBS = [
    ("dbA", "file:/Users/georgeskhawam/Projects/dedupe_db/music.db?mode=ro&immutable=1"),
    ("dbB", "file:/Users/georgeskhawam/Projects/dedupe_db/CANONICAL/music_CANONICAL_2026-01-06.db?mode=ro&immutable=1"),
    ("dbC", "file:/Volumes/RECOVERY_TARGET/Root/Projects2/dedupe_repo_reclone/artifacts/db/music.db?mode=ro&immutable=1"),
]

PREFIXES = [
    "/Volumes/COMMUNE/R2",
    "/Volumes/COMMUNE/Root",
    "/Volumes/COMMUNE/_PROMOTION_STAGING",
    "/Volumes/RECOVERY_TARGET/Root",
    "/Volumes/Vault/RC2",
    "/Volumes/Vault/RECOVERED_TRASH",
    "/Volumes/Vault/Root",
    "/Volumes/Vault/Vault",
    "/Volumes/bad/.dedupe_db",
    "/Volumes/bad/FINAL_LIBRARY",
    "/Volumes/bad/_ALL_FLACS_FLAT",
    "/Volumes/bad/_BAD_VS_DOTAD_DISCARDS",
]

missing_paths = []
with FS_EXISTENCE.open(newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row.get("exists") == "0":
            missing_paths.append(row["path"])
missing_paths = sorted(set(missing_paths))

conn = sqlite3.connect(":memory:")
cur = conn.cursor()
for name, uri in DBS:
    cur.execute(f"ATTACH DATABASE '{uri}' AS {name};")

cur.execute("CREATE TEMP TABLE missing_paths(path TEXT PRIMARY KEY);")
cur.executemany("INSERT OR IGNORE INTO missing_paths(path) VALUES (?);", [(p,) for p in missing_paths])

path_checksums = {p: set() for p in missing_paths}
for name, _ in DBS:
    for path, checksum in cur.execute(
        f"SELECT path, checksum FROM {name}.files WHERE path IN (SELECT path FROM missing_paths);"
    ):
        path_checksums.setdefault(path, set()).add(checksum)

path_seen = {}
for name, _ in DBS[:2]:
    for path, first_seen, last_seen in cur.execute(
        f"""
        SELECT path, MIN(created_at) AS first_seen, MAX(created_at) AS last_seen
        FROM {name}.file_scan_runs
        WHERE path IN (SELECT path FROM missing_paths)
        GROUP BY path;
        """
    ):
        existing = path_seen.get(path)
        if existing is None:
            path_seen[path] = (first_seen, last_seen)
        else:
            prev_first, prev_last = existing
            merged_first = min(filter(None, [prev_first, first_seen]), default=None)
            merged_last = max(filter(None, [prev_last, last_seen]), default=None)
            path_seen[path] = (merged_first, merged_last)

needed_checksums = sorted({
    c for checksums in path_checksums.values() for c in checksums if c is not None
})
cur.execute("CREATE TEMP TABLE needed_checksums(checksum TEXT PRIMARY KEY);")
cur.executemany(
    "INSERT OR IGNORE INTO needed_checksums(checksum) VALUES (?);",
    [(c,) for c in needed_checksums],
)

matches_by_checksum = {c: set() for c in needed_checksums}
for name, _ in DBS:
    for checksum, path in cur.execute(
        f"SELECT checksum, path FROM {name}.files WHERE checksum IN (SELECT checksum FROM needed_checksums);"
    ):
        if path == PREFIX or path.startswith(PREFIX + "/"):
            continue
        matches_by_checksum.setdefault(checksum, set()).add(path)

prefixes_by_len = sorted(PREFIXES, key=len, reverse=True)

def match_prefix(path):
    for prefix in prefixes_by_len:
        if path == prefix or path.startswith(prefix + "/"):
            return prefix
    return None

def relative_path(path):
    if path == PREFIX:
        return ""
    if path.startswith(PREFIX + "/"):
        return path[len(PREFIX) + 1 :]
    return path

def checksum_sort_key(value):
    return (value is None, "" if value is None else value)

rows = []
for path in sorted(missing_paths):
    rel = relative_path(path)
    checksums = path_checksums.get(path) or {None}
    first_seen, last_seen = path_seen.get(path, (None, None))
    for checksum in sorted(checksums, key=checksum_sort_key):
        matches = sorted(matches_by_checksum.get(checksum, set())) if checksum else []
        if matches:
            for match_path in matches:
                rows.append([
                    rel,
                    checksum,
                    first_seen,
                    last_seen,
                    match_prefix(match_path),
                    match_path,
                ])
        else:
            rows.append([
                rel,
                checksum,
                first_seen,
                last_seen,
                "",
                "",
            ])

with OUT_MAIN.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "relative_path",
        "checksum",
        "first_seen",
        "last_seen",
        "match_prefix",
        "match_path",
    ])
    for row in rows:
        writer.writerow(row)

# Summary counts: how many missing paths have checksum matches in other prefixes.
missing_with_match = set()
for path in missing_paths:
    checksums = path_checksums.get(path) or {None}
    for checksum in checksums:
        if checksum and matches_by_checksum.get(checksum):
            missing_with_match.add(path)
            break

summary_rows = [
    ["total_missing", len(missing_paths)],
    ["with_checksum_twin", len(missing_with_match)],
    ["without_checksum_twin", len(missing_paths) - len(missing_with_match)],
]
with OUT_SUMMARY.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["metric", "count"])
    writer.writerows(summary_rows)

conn.close()

# Output file checksums for deterministic auditing.
def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

for path in (OUT_MAIN, OUT_SUMMARY):
    with path.open(newline="") as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1
    print(f"{path}\t{row_count}\t{file_sha256(path)}")
