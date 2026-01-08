#!/usr/bin/env python3
# Proves: checksum-based matches between orphaned missing paths and files under /Volumes/RECOVERY_TARGET/_QUARANTINE.
# Does not prove: provenance beyond checksum equality or any correctness outside the input CSVs and computed hashes.

import csv
import hashlib
import os
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")
ORPHANS = BASE / "missing_paths_bucket_orphans_ro_bad_commune_vault.csv"
COLLAPSE = BASE / "missing_paths_checksum_twin_collapse_ro_bad_commune_vault.csv"
INVENTORY = BASE / "quarantine_inventory.csv"

OUT_QUARANTINE_HASHES = BASE / "quarantine_checksums.csv"
OUT_MATCHES = BASE / "orphans_in_quarantine_by_checksum.csv"
OUT_UNMATCHED = BASE / "orphans_checksum_no_quarantine_match.csv"
OUT_SUMMARY = BASE / "orphans_quarantine_checksum_summary.csv"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_hex(value: str) -> bool:
    return all(c in "0123456789abcdefABCDEF" for c in value)


def detect_algo(value: str) -> str | None:
    if not value:
        return None
    if not is_hex(value):
        return None
    length = len(value)
    if length == 32:
        return "md5"
    if length == 40:
        return "sha1"
    if length == 64:
        return "sha256"
    return None


def file_hashes(path: Path, algos: set[str]) -> dict:
    hashes = {}
    md5 = hashlib.md5() if "md5" in algos else None
    sha1 = hashlib.sha1() if "sha1" in algos else None
    sha256 = hashlib.sha256() if "sha256" in algos else None
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if md5:
                md5.update(chunk)
            if sha1:
                sha1.update(chunk)
            if sha256:
                sha256.update(chunk)
    if md5:
        hashes["md5"] = md5.hexdigest()
    if sha1:
        hashes["sha1"] = sha1.hexdigest()
    if sha256:
        hashes["sha256"] = sha256.hexdigest()
    return hashes


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

required_algos = set()
# Load checksum mapping for orphans
orphan_checksums = {}
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
        orphan_checksums[rel] = checksums
        for checksum in checksums:
            algo = detect_algo(checksum)
            if algo:
                required_algos.add(algo)

# Load quarantine inventory
quarantine_files = []
with INVENTORY.open(newline="") as f:
    reader = csv.DictReader(f)
    required = {"path", "basename", "size", "mtime"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"Missing required columns in {INVENTORY}: {sorted(missing)}")
    for row in reader:
        path = row.get("path")
        if not path:
            continue
        quarantine_files.append((Path(path), row.get("size"), row.get("mtime")))

quarantine_files.sort(key=lambda x: str(x[0]))

# Compute hashes for quarantine files
hash_map = {algo: {} for algo in required_algos}
quarantine_hash_rows = []
for path, size, mtime in quarantine_files:
    if not path.exists():
        continue
    hashes = file_hashes(path, required_algos)
    md5_hex = hashes.get("md5", "")
    sha1_hex = hashes.get("sha1", "")
    sha256_hex = hashes.get("sha256", "")
    quarantine_hash_rows.append([str(path), size, mtime, md5_hex, sha1_hex, sha256_hex])

    for algo, digest in hashes.items():
        hash_map[algo].setdefault(digest, []).append((str(path), size, mtime))

# Write quarantine checksums inventory
with OUT_QUARANTINE_HASHES.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["path", "size", "mtime", "md5", "sha1", "sha256"])
    for row in quarantine_hash_rows:
        writer.writerow(row)

# Match orphans by checksum
match_rows = []
unmatched_rows = []

for rel in sorted(orphan_paths):
    checksums = orphan_checksums.get(rel, [])
    if not checksums:
        unmatched_rows.append([rel, "", "unknown_checksum"])
        continue
    for checksum in checksums:
        algo = detect_algo(checksum)
        if not algo:
            unmatched_rows.append([rel, checksum, "unsupported_checksum_format"])
            continue
        matches = hash_map.get(algo, {}).get(checksum, [])
        if not matches:
            unmatched_rows.append([rel, checksum, f"no_{algo}_match"])
            continue
        for path, size, mtime in matches:
            match_rows.append([rel, checksum, algo, path, size, mtime])

# Write matches
with OUT_MATCHES.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "relative_path",
        "checksum",
        "algorithm",
        "quarantine_path",
        "quarantine_size",
        "quarantine_mtime",
    ])
    for row in match_rows:
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
    ["quarantine_files_hashed", len(quarantine_hash_rows)],
]
with OUT_SUMMARY.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["metric", "count"])
    writer.writerows(summary_rows)

# Verification output
for path in (OUT_QUARANTINE_HASHES, OUT_MATCHES, OUT_UNMATCHED, OUT_SUMMARY):
    with path.open(newline="") as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1
    print(f"{path}\t{row_count}\t{sha256_path(path)}")
