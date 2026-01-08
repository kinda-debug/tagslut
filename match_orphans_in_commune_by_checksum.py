#!/usr/bin/env python3
# Proves: checksum-based matches between orphaned missing paths and files under /Volumes/COMMUNE using SHA-256.
# Does not prove: provenance beyond checksum equality or any correctness outside the input CSVs and computed hashes.

import csv
import hashlib
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")
ORPHANS = BASE / "missing_paths_bucket_orphans_ro_bad_commune_vault.csv"
COLLAPSE = BASE / "missing_paths_checksum_twin_collapse_ro_bad_commune_vault.csv"
COMMUNE_HASHES = BASE / "commune_flac_sha256.csv"

OUT_MATCHES = BASE / "orphans_in_commune_by_checksum.csv"
OUT_UNMATCHED = BASE / "orphans_checksum_no_commune_match.csv"
OUT_SUMMARY = BASE / "orphans_commune_checksum_summary.csv"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_hex(value: str) -> bool:
    return all(c in "0123456789abcdefABCDEF" for c in value)


def is_sha256(value: str) -> bool:
    return len(value) == 64 and is_hex(value)


# Load orphan paths
orphan_paths = set()
with ORPHANS.open(newline="") as f:
    reader = csv.DictReader(f)
    if "relative_path" not in (reader.fieldnames or []):
        raise SystemExit(f"Missing relative_path column in {ORPHANS}")
    for row in reader:
        rel = row.get("relative_path")
        if rel:
            orphan_paths.add(rel)

# Load orphan checksums (sha256 only)
orphan_checksums = {}
for rel in sorted(orphan_paths):
    orphan_checksums[rel] = []

with COLLAPSE.open(newline="") as f:
    reader = csv.DictReader(f)
    if "relative_path" not in (reader.fieldnames or []) or "checksum" not in (reader.fieldnames or []):
        raise SystemExit(f"Missing required columns in {COLLAPSE}")
    for row in reader:
        rel = row.get("relative_path")
        if rel not in orphan_paths:
            continue
        checksum_value = row.get("checksum") or ""
        checksums = [c for c in checksum_value.split(";") if c]
        for checksum in checksums:
            if is_sha256(checksum):
                orphan_checksums[rel].append(checksum)
            else:
                orphan_checksums[rel].append(checksum)

# Load commune hashes into map
commune_hash_map = {}
commune_rows = 0
with COMMUNE_HASHES.open(newline="") as f:
    reader = csv.DictReader(f)
    required = {"path", "size", "mtime", "sha256"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"Missing required columns in {COMMUNE_HASHES}: {sorted(missing)}")
    for row in reader:
        digest = row.get("sha256") or ""
        if not digest:
            continue
        commune_hash_map.setdefault(digest, []).append(
            (row.get("path"), row.get("size"), row.get("mtime"))
        )
        commune_rows += 1

for digest in commune_hash_map:
    commune_hash_map[digest].sort(key=lambda x: x[0] or "")

# Match orphans by checksum
match_rows = []
unmatched_rows = []

for rel in sorted(orphan_paths):
    checksums = orphan_checksums.get(rel, [])
    if not checksums:
        unmatched_rows.append([rel, "", "unknown_checksum"])
        continue
    for checksum in checksums:
        if not is_sha256(checksum):
            unmatched_rows.append([rel, checksum, "unsupported_checksum_format"])
            continue
        matches = commune_hash_map.get(checksum, [])
        if not matches:
            unmatched_rows.append([rel, checksum, "no_sha256_match"])
            continue
        for path, size, mtime in matches:
            match_rows.append([rel, checksum, path, size, mtime])

# Write matches
with OUT_MATCHES.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "relative_path",
        "checksum",
        "commune_path",
        "commune_size",
        "commune_mtime",
    ])
    for row in sorted(match_rows, key=lambda x: (x[0], x[1], x[2] or "")):
        writer.writerow(row)

# Write unmatched
with OUT_UNMATCHED.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["relative_path", "checksum", "reason"])
    for row in unmatched_rows:
        writer.writerow(row)

# Summary
summary_rows = [
    ["orphans_total", len(orphan_paths)],
    ["orphan_checksums_with_matches", len({r[0] for r in match_rows})],
    ["match_rows", len(match_rows)],
    ["unmatched_rows", len(unmatched_rows)],
    ["commune_files_hashed", commune_rows],
]
with OUT_SUMMARY.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["metric", "count"])
    writer.writerows(summary_rows)

# Verification output
for path in (OUT_MATCHES, OUT_UNMATCHED, OUT_SUMMARY):
    with path.open(newline="") as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1
    print(f"{path}\t{row_count}\t{sha256_path(path)}")
