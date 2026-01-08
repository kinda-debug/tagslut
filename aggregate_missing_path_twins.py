#!/usr/bin/env python3
# Proves: deterministic aggregation of existing CSV artifacts into prefix- and path-level checksum-twin summaries.
# Does not prove: filesystem existence, checksum correctness, or any provenance beyond the input CSV contents.

import csv
import hashlib
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")
INPUT_MATCHES = BASE / "missing_paths_RECOVERY_TARGET_checksum_matches.csv"
INPUT_SUMMARY = BASE / "missing_paths_RECOVERY_TARGET_checksum_twin_summary.csv"

OUT_BY_PREFIX = BASE / "missing_paths_checksum_twins_by_prefix.csv"
OUT_COLLAPSE = BASE / "missing_paths_checksum_twin_collapse.csv"
OUT_ORPHANS = BASE / "missing_paths_without_any_checksum_twin.csv"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_empty(value) -> bool:
    return value is None or value == ""


# Aggregation structures
all_paths = set()
paths_with_match = set()
per_path_checksums = {}
per_path_match_prefixes = {}
per_path_match_paths = {}
per_path_checksum_prefix = {}

# Step 1 dedup per (relative_path, checksum, match_prefix)
dedup_triplets = set()
prefix_to_paths = {}
prefix_to_checksums = {}
prefix_to_rows = {}

with INPUT_MATCHES.open(newline="") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames or []
    required = {"relative_path", "checksum", "match_prefix"}
    missing = required - set(fields)
    if missing:
        raise SystemExit(f"Missing required columns in {INPUT_MATCHES}: {sorted(missing)}")

    has_match_path = "match_path" in fields

    for row in reader:
        rel = row.get("relative_path")
        checksum = row.get("checksum")
        match_prefix = row.get("match_prefix")
        match_path = row.get("match_path") if has_match_path else ""

        if rel is None:
            continue

        all_paths.add(rel)

        if not is_empty(checksum):
            per_path_checksums.setdefault(rel, set()).add(checksum)

        if not is_empty(match_prefix):
            per_path_match_prefixes.setdefault(rel, set()).add(match_prefix)

        if has_match_path and not is_empty(match_path):
            per_path_match_paths.setdefault(rel, set()).add(match_path)

        if (has_match_path and not is_empty(match_path)) or (not is_empty(match_prefix)):
            paths_with_match.add(rel)

        if not is_empty(match_prefix):
            triplet = (rel, checksum, match_prefix)
            if triplet not in dedup_triplets:
                dedup_triplets.add(triplet)
                prefix_to_paths.setdefault(match_prefix, set()).add(rel)
                if not is_empty(checksum):
                    prefix_to_checksums.setdefault(match_prefix, set()).add(checksum)
                prefix_to_rows[match_prefix] = prefix_to_rows.get(match_prefix, 0) + 1
                per_path_checksum_prefix.setdefault(rel, set()).add((checksum, match_prefix))


# Step 1: Aggregate by prefix
with OUT_BY_PREFIX.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["match_prefix", "missing_path_count", "unique_checksums", "total_match_rows"])

    rows = []
    for prefix in prefix_to_paths:
        missing_path_count = len(prefix_to_paths.get(prefix, set()))
        unique_checksums = len(prefix_to_checksums.get(prefix, set()))
        total_match_rows = prefix_to_rows.get(prefix, 0)
        rows.append((prefix, missing_path_count, unique_checksums, total_match_rows))

    rows.sort(key=lambda x: (-x[1], x[0]))
    for row in rows:
        writer.writerow(row)


# Step 2: Per-missing-path collapse
with OUT_COLLAPSE.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "relative_path",
        "checksum",
        "twin_count",
        "prefix_count",
        "prefixes",
        "first_seen_prefix",
        "last_seen_prefix",
    ])

    for rel in sorted(all_paths):
        checksums = sorted(per_path_checksums.get(rel, set()))
        checksum_value = ""
        if len(checksums) == 1:
            checksum_value = checksums[0]
        elif len(checksums) > 1:
            checksum_value = ";".join(checksums)

        prefixes = sorted(per_path_match_prefixes.get(rel, set()))
        prefix_count = len(prefixes)
        prefixes_value = ",".join(prefixes)
        first_seen_prefix = prefixes[0] if prefixes else ""
        last_seen_prefix = prefixes[-1] if prefixes else ""

        if rel in per_path_match_paths:
            twin_count = len(per_path_match_paths.get(rel, set()))
        else:
            twin_count = len(per_path_checksum_prefix.get(rel, set()))

        writer.writerow([
            rel,
            checksum_value,
            twin_count,
            prefix_count,
            prefixes_value,
            first_seen_prefix,
            last_seen_prefix,
        ])


# Step 3: Orphan detection
orphans = sorted(all_paths - paths_with_match)
with OUT_ORPHANS.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["relative_path"])
    for rel in orphans:
        writer.writerow([rel])


# Step 4: Verification output
outputs = [OUT_BY_PREFIX, OUT_COLLAPSE, OUT_ORPHANS]
inputs = [INPUT_MATCHES, INPUT_SUMMARY]

print("Inputs (sha256):")
for path in inputs:
    print(f"{path}\t{sha256_path(path)}")

print("Outputs (rows, sha256):")
for path in outputs:
    with path.open(newline="") as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1
    print(f"{path}\t{row_count}\t{sha256_path(path)}")

print("Integrity Notes:")
print("no DB access performed")
print("no filesystem access performed")
print("no rows dropped except via explicit deduplication rules above")
