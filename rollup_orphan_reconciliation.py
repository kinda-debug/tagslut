#!/usr/bin/env python3
# Proves: a deterministic, per-orphan rollup of checksum match evidence from existing CSV artifacts.
# Does not prove: filesystem existence, provenance, or correctness beyond the input CSV contents.

import csv
import hashlib
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")
ORPHANS = BASE / "missing_paths_bucket_orphans_ro_bad_commune_vault.csv"
COLLAPSE = BASE / "missing_paths_checksum_twin_collapse_ro_bad_commune_vault.csv"
RECON = BASE / "orphans_reconciliation_quarantine_commune.csv"

OUT_ROLLUP = BASE / "orphans_reconciliation_rollup.csv"
OUT_SUMMARY = BASE / "orphans_reconciliation_rollup_summary.csv"


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

# Load checksum map
checksum_map = {rel: "" for rel in orphan_paths}
with COLLAPSE.open(newline="") as f:
    reader = csv.DictReader(f)
    required = {"relative_path", "checksum"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"Missing required columns in {COLLAPSE}: {sorted(missing)}")
    for row in reader:
        rel = row.get("relative_path")
        if rel in checksum_map:
            checksum_map[rel] = row.get("checksum") or ""

# Aggregate reconciliation evidence
per_orphan = {}
with RECON.open(newline="") as f:
    reader = csv.DictReader(f)
    required = {
        "relative_path",
        "checksum",
        "source",
        "source_path",
        "source_size",
        "source_mtime",
        "evidence",
    }
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"Missing required columns in {RECON}: {sorted(missing)}")
    for row in reader:
        rel = row.get("relative_path")
        if rel not in orphan_paths:
            continue
        entry = per_orphan.setdefault(
            rel,
            {
                "sources": set(),
                "match_rows": 0,
                "source_paths": set(),
                "source_counts": {},
            },
        )
        source = row.get("source") or ""
        source_path = row.get("source_path") or ""
        entry["sources"].add(source)
        entry["match_rows"] += 1
        if source_path:
            entry["source_paths"].add(source_path)
        entry["source_counts"][source] = entry["source_counts"].get(source, 0) + 1

# Write rollup
with OUT_ROLLUP.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "relative_path",
        "checksum",
        "match_rows",
        "source_count",
        "sources",
        "quarantine_match_rows",
        "commune_match_rows",
        "source_path_count",
        "status",
    ])

    for rel in sorted(orphan_paths):
        entry = per_orphan.get(rel, {})
        sources = sorted(entry.get("sources", set()))
        match_rows = entry.get("match_rows", 0)
        source_count = len(sources)
        sources_value = ",".join(sources)
        source_paths = entry.get("source_paths", set())
        source_path_count = len(source_paths)
        source_counts = entry.get("source_counts", {})
        quarantine_rows = source_counts.get("quarantine", 0)
        commune_rows = source_counts.get("commune", 0)
        status = "matched" if match_rows > 0 else "unmatched"
        writer.writerow([
            rel,
            checksum_map.get(rel, ""),
            match_rows,
            source_count,
            sources_value,
            quarantine_rows,
            commune_rows,
            source_path_count,
            status,
        ])

# Summary
with_any_match = sum(1 for rel in orphan_paths if per_orphan.get(rel, {}).get("match_rows", 0) > 0)
without_match = len(orphan_paths) - with_any_match
with_quarantine = sum(
    1 for rel in orphan_paths if per_orphan.get(rel, {}).get("source_counts", {}).get("quarantine", 0) > 0
)
with_commune = sum(
    1 for rel in orphan_paths if per_orphan.get(rel, {}).get("source_counts", {}).get("commune", 0) > 0
)
with_both = sum(
    1
    for rel in orphan_paths
    if per_orphan.get(rel, {}).get("source_counts", {}).get("quarantine", 0) > 0
    and per_orphan.get(rel, {}).get("source_counts", {}).get("commune", 0) > 0
)

summary_rows = [
    ["orphans_total", len(orphan_paths)],
    ["with_any_match", with_any_match],
    ["without_match", without_match],
    ["with_quarantine_match", with_quarantine],
    ["with_commune_match", with_commune],
    ["with_both_sources", with_both],
]
with OUT_SUMMARY.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["metric", "count"])
    writer.writerows(summary_rows)

# Verification output
for path in (OUT_ROLLUP, OUT_SUMMARY):
    with path.open(newline="") as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1
    print(f"{path}\t{row_count}\t{sha256_path(path)}")
