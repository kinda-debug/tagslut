#!/usr/bin/env python3
# Proves: sidecar reconciliation of orphaned missing paths to on-disk files using checksum equality.
# Does not prove: provenance beyond checksum matches or any correctness outside the input CSVs and computed hashes.

import csv
import hashlib
import os
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")
ORPHANS = BASE / "missing_paths_bucket_orphans_ro_bad_commune_vault.csv"
COLLAPSE = BASE / "missing_paths_checksum_twin_collapse_ro_bad_commune_vault.csv"
QUARANTINE_HASHES = BASE / "quarantine_checksums.csv"

OUT_SIDECAR = BASE / "orphans_sidecar_reconciliation.csv"
OUT_SUMMARY = BASE / "orphans_sidecar_reconciliation_summary.csv"

EXISTENCE_FILES = [
    ("bad", BASE / "fs_existence_ro_Volumes__bad__.dedupe_db.csv"),
    ("bad", BASE / "fs_existence_ro_Volumes__bad__FINAL_LIBRARY.csv"),
    ("bad", BASE / "fs_existence_ro_Volumes__bad___ALL_FLACS_FLAT.csv"),
    ("bad", BASE / "fs_existence_ro_Volumes__bad___BAD_VS_DOTAD_DISCARDS.csv"),
    ("commune", BASE / "fs_existence_ro_Volumes__COMMUNE__R2.csv"),
    ("commune", BASE / "fs_existence_ro_Volumes__COMMUNE__Root.csv"),
    ("commune", BASE / "fs_existence_ro_Volumes__COMMUNE___PROMOTION_STAGING.csv"),
    ("vault", BASE / "fs_existence_ro_Volumes__Vault__RC2.csv"),
    ("vault", BASE / "fs_existence_ro_Volumes__Vault__RECOVERED_TRASH.csv"),
    ("vault", BASE / "fs_existence_ro_Volumes__Vault__Root.csv"),
    ("vault", BASE / "fs_existence_ro_Volumes__Vault__Vault.csv"),
]


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# Load orphan set
orphan_paths = set()
with ORPHANS.open(newline="") as f:
    reader = csv.DictReader(f)
    if "relative_path" not in (reader.fieldnames or []):
        raise SystemExit(f"Missing relative_path column in {ORPHANS}")
    for row in reader:
        rel = row.get("relative_path")
        if rel:
            orphan_paths.add(rel)

# Load orphan checksums (sha256)
orphan_checksum_by_rel = {}
orphan_rels_by_checksum = {}
orphan_basenames = set()
with COLLAPSE.open(newline="") as f:
    reader = csv.DictReader(f)
    if "relative_path" not in (reader.fieldnames or []) or "checksum" not in (reader.fieldnames or []):
        raise SystemExit(f"Missing required columns in {COLLAPSE}")
    for row in reader:
        rel = row.get("relative_path")
        if rel not in orphan_paths:
            continue
        checksum = row.get("checksum") or ""
        if not checksum:
            continue
        orphan_checksum_by_rel[rel] = checksum
        orphan_rels_by_checksum.setdefault(checksum, set()).add(rel)
        orphan_basenames.add(os.path.basename(rel))

# Sidecar rows
rows = []
matched_orphans = set()
source_counts = {"quarantine": 0, "bad": 0, "commune": 0, "vault": 0}

# Use existing quarantine checksums (no re-hash)
with QUARANTINE_HASHES.open(newline="") as f:
    reader = csv.DictReader(f)
    required = {"path", "size", "mtime", "sha256"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"Missing required columns in {QUARANTINE_HASHES}: {sorted(missing)}")
    for row in reader:
        digest = row.get("sha256") or ""
        if digest in orphan_rels_by_checksum:
            for rel in sorted(orphan_rels_by_checksum[digest]):
                rows.append([
                    rel,
                    digest,
                    "quarantine",
                    row.get("path"),
                    digest,
                    row.get("size"),
                    row.get("mtime"),
                    "sha256",
                ])
                matched_orphans.add(rel)
                source_counts["quarantine"] += 1

# Hash candidate files from other volumes using basename filter
for source, csv_path in EXISTENCE_FILES:
    if not csv_path.exists():
        raise SystemExit(f"Missing existence file: {csv_path}")
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        if "path" not in (reader.fieldnames or []) or "exists" not in (reader.fieldnames or []):
            raise SystemExit(f"Missing required columns in {csv_path}")
        for row in reader:
            if row.get("exists") != "1":
                continue
            path_str = row.get("path")
            if not path_str:
                continue
            base = os.path.basename(path_str)
            if base not in orphan_basenames:
                continue
            file_path = Path(path_str)
            try:
                digest = file_sha256(file_path)
            except OSError:
                continue
            if digest not in orphan_rels_by_checksum:
                continue
            try:
                st = file_path.stat()
                size = st.st_size
                mtime = st.st_mtime
            except OSError:
                size = None
                mtime = None
            for rel in sorted(orphan_rels_by_checksum[digest]):
                rows.append([
                    rel,
                    digest,
                    source,
                    str(file_path),
                    digest,
                    size,
                    mtime,
                    "sha256",
                ])
                matched_orphans.add(rel)
                source_counts[source] += 1

# Write sidecar
with OUT_SIDECAR.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "relative_path",
        "orphan_checksum",
        "source",
        "source_path",
        "source_checksum",
        "source_size",
        "source_mtime",
        "evidence",
    ])
    for row in sorted(rows, key=lambda x: (x[0], x[2], x[3] or "")):
        writer.writerow(row)

# Summary
summary_rows = [
    ["orphans_total", len(orphan_paths)],
    ["orphans_with_sidecar_match", len(matched_orphans)],
    ["orphans_without_sidecar_match", len(orphan_paths) - len(matched_orphans)],
    ["matches_quarantine", source_counts["quarantine"]],
    ["matches_bad", source_counts["bad"]],
    ["matches_commune", source_counts["commune"]],
    ["matches_vault", source_counts["vault"]],
]
with OUT_SUMMARY.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["metric", "count"])
    writer.writerows(summary_rows)

# Verification output
for path in (OUT_SIDECAR, OUT_SUMMARY):
    with path.open(newline="") as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1
    print(f"{path}\t{row_count}\t{sha256_path(path)}")
