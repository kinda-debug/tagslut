#!/usr/bin/env python3
# Proves: partitions missing paths into three buckets based on checksum twin locations in the match CSV.
# Does not prove: filesystem correctness, checksum validity, or provenance beyond input CSV contents.

import csv
import hashlib
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")
INPUT_MATCHES = BASE / "missing_paths_RECOVERY_TARGET_checksum_matches_ro_bad.csv"
INPUT_ORPHANS = BASE / "missing_paths_without_any_checksum_twin_ro_bad.csv"

OUT_BAD_PRESENT = BASE / "missing_paths_bucket_bad_present.csv"
OUT_OTHER_TWINS = BASE / "missing_paths_bucket_other_twins.csv"
OUT_ORPHANS = BASE / "missing_paths_bucket_orphans.csv"

BAD_PREFIX = "/Volumes/bad/"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# Load orphans set for consistency check
orphans_set = set()
with INPUT_ORPHANS.open(newline="") as f:
    reader = csv.DictReader(f)
    if "relative_path" not in (reader.fieldnames or []):
        raise SystemExit(f"Missing relative_path column in {INPUT_ORPHANS}")
    for row in reader:
        rel = row.get("relative_path")
        if rel is not None:
            orphans_set.add(rel)

# Build per-path metadata
all_paths = set()
path_has_any_match = {}
path_bad_present = {}
path_bad_prefixes = {}
path_other_prefixes = {}
path_bad_match_count = {}

with INPUT_MATCHES.open(newline="") as f:
    reader = csv.DictReader(f)
    fields = reader.fieldnames or []
    required = {"relative_path", "match_prefix", "match_exists"}
    missing = required - set(fields)
    if missing:
        raise SystemExit(f"Missing required columns in {INPUT_MATCHES}: {sorted(missing)}")

    has_match_path = "match_path" in fields

    for row in reader:
        rel = row.get("relative_path")
        if rel is None:
            continue
        all_paths.add(rel)

        match_prefix = row.get("match_prefix") or ""
        match_exists = row.get("match_exists") or ""
        match_path = row.get("match_path") if has_match_path else ""

        if match_prefix:
            path_has_any_match[rel] = True
            if match_prefix.startswith(BAD_PREFIX) and match_exists == "1":
                path_bad_present[rel] = True
                path_bad_prefixes.setdefault(rel, set()).add(match_prefix)
                if match_path:
                    path_bad_match_count[rel] = path_bad_match_count.get(rel, set()) | {match_path}
            elif not match_prefix.startswith(BAD_PREFIX):
                path_other_prefixes.setdefault(rel, set()).add(match_prefix)

# Consistency check for orphans
computed_orphans = {p for p in all_paths if not path_has_any_match.get(p)}
if computed_orphans != orphans_set:
    raise SystemExit(
        "Orphan set mismatch between computed and existing orphan file. "
        f"computed={len(computed_orphans)} file={len(orphans_set)}"
    )

# Bucket 1: confirmed twins on /Volumes/bad
bucket_bad_present = sorted(p for p in all_paths if path_bad_present.get(p))

# Bucket 2: twins exist, but none confirmed on /Volumes/bad
bucket_other_twins = sorted(
    p for p in all_paths if path_has_any_match.get(p) and not path_bad_present.get(p)
)

# Bucket 3: orphans (no twins)
bucket_orphans = sorted(computed_orphans)

# Write bucket 1
with OUT_BAD_PRESENT.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["relative_path", "bad_prefix_count", "bad_prefixes", "bad_match_path_count"])
    for rel in bucket_bad_present:
        bad_prefixes = sorted(path_bad_prefixes.get(rel, set()))
        bad_prefix_count = len(bad_prefixes)
        bad_match_paths = path_bad_match_count.get(rel, set())
        writer.writerow([
            rel,
            bad_prefix_count,
            ";".join(bad_prefixes),
            len(bad_match_paths),
        ])

# Write bucket 2
with OUT_OTHER_TWINS.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["relative_path", "other_prefix_count", "other_prefixes"])
    for rel in bucket_other_twins:
        other_prefixes = sorted(path_other_prefixes.get(rel, set()))
        writer.writerow([
            rel,
            len(other_prefixes),
            ";".join(other_prefixes),
        ])

# Write bucket 3
with OUT_ORPHANS.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["relative_path"])
    for rel in bucket_orphans:
        writer.writerow([rel])

# Verification output
for path in (OUT_BAD_PRESENT, OUT_OTHER_TWINS, OUT_ORPHANS):
    with path.open(newline="") as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1
    print(f"{path}\t{row_count}\t{sha256_path(path)}")
