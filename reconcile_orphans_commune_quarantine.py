#!/usr/bin/env python3
# Proves: consolidates existing checksum-match CSVs (COMMUNE + QUARANTINE) into unified reconciliation outputs.
# Does not prove: filesystem existence, provenance, or correctness beyond the input CSV contents.

import csv
import hashlib
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")
ORPHANS = BASE / "missing_paths_bucket_orphans_ro_bad_commune_vault.csv"
COLLAPSE = BASE / "missing_paths_checksum_twin_collapse_ro_bad_commune_vault.csv"
COMMUNE_MATCHES = BASE / "orphans_in_commune_by_checksum.csv"
QUAR_MATCHES = BASE / "orphans_in_quarantine_by_checksum.csv"

OUT_RECON = BASE / "orphans_reconciliation_quarantine_commune.csv"
OUT_UNMATCHED = BASE / "orphans_without_quarantine_or_commune_match.csv"
OUT_COLLISIONS = BASE / "orphans_commune_checksum_collisions.csv"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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

# Load orphan checksum map (as stored in collapse)
orphan_checksum_map = {rel: "" for rel in orphan_paths}
with COLLAPSE.open(newline="") as f:
    reader = csv.DictReader(f)
    required = {"relative_path", "checksum"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"Missing required columns in {COLLAPSE}: {sorted(missing)}")
    for row in reader:
        rel = row.get("relative_path")
        if rel in orphan_checksum_map:
            orphan_checksum_map[rel] = row.get("checksum") or ""

# Consolidate matches
recon_rows = set()
matched_rel = set()

with COMMUNE_MATCHES.open(newline="") as f:
    reader = csv.DictReader(f)
    required = {"relative_path", "checksum", "commune_path", "commune_size", "commune_mtime"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"Missing required columns in {COMMUNE_MATCHES}: {sorted(missing)}")
    for row in reader:
        rel = row.get("relative_path")
        if rel not in orphan_paths:
            continue
        checksum = row.get("checksum") or ""
        path = row.get("commune_path") or ""
        size = row.get("commune_size") or ""
        mtime = row.get("commune_mtime") or ""
        recon_rows.add((rel, checksum, "commune", path, size, mtime, "sha256"))
        matched_rel.add(rel)

with QUAR_MATCHES.open(newline="") as f:
    reader = csv.DictReader(f)
    required = {
        "relative_path",
        "checksum",
        "algorithm",
        "quarantine_path",
        "quarantine_size",
        "quarantine_mtime",
    }
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"Missing required columns in {QUAR_MATCHES}: {sorted(missing)}")
    for row in reader:
        rel = row.get("relative_path")
        if rel not in orphan_paths:
            continue
        checksum = row.get("checksum") or ""
        path = row.get("quarantine_path") or ""
        size = row.get("quarantine_size") or ""
        mtime = row.get("quarantine_mtime") or ""
        algo = row.get("algorithm") or ""
        recon_rows.add((rel, checksum, "quarantine", path, size, mtime, algo))
        matched_rel.add(rel)

# Write consolidated reconciliation
with OUT_RECON.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "relative_path",
        "checksum",
        "source",
        "source_path",
        "source_size",
        "source_mtime",
        "evidence",
    ])
    for row in sorted(recon_rows, key=lambda x: (x[0], x[2], x[3])):
        writer.writerow(row)

# Write unmatched after COMMUNE + QUARANTINE
unmatched_rows = []
for rel in sorted(orphan_paths):
    if rel in matched_rel:
        continue
    unmatched_rows.append((rel, orphan_checksum_map.get(rel, "")))

with OUT_UNMATCHED.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["relative_path", "checksum"])
    for row in unmatched_rows:
        writer.writerow(row)

# Commune collision report (same orphan checksum matched to multiple commune paths)
collisions = []
commune_map = {}
with COMMUNE_MATCHES.open(newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        rel = row.get("relative_path")
        if rel not in orphan_paths:
            continue
        checksum = row.get("checksum") or ""
        path = row.get("commune_path") or ""
        commune_map.setdefault((rel, checksum), set()).add(path)

for (rel, checksum), paths in commune_map.items():
    unique_paths = sorted(p for p in paths if p)
    if len(unique_paths) > 1:
        collisions.append((rel, checksum, len(unique_paths), ",".join(unique_paths)))

with OUT_COLLISIONS.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["relative_path", "checksum", "commune_match_count", "commune_paths"])
    for row in sorted(collisions, key=lambda x: (x[0], x[1])):
        writer.writerow(row)

# Verification output
for path in (OUT_RECON, OUT_UNMATCHED, OUT_COLLISIONS):
    with path.open(newline="") as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1
    print(f"{path}\t{row_count}\t{sha256_path(path)}")
