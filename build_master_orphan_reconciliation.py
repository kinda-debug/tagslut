#!/usr/bin/env python3
# Proves: consolidates reconciliation evidence into a single master CSV with a deterministic best-evidence flag.
# Does not prove: filesystem existence, provenance, or correctness beyond the input CSV contents.

import csv
import hashlib
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")
ROLLUP = BASE / "orphans_reconciliation_rollup.csv"
RECON = BASE / "orphans_reconciliation_quarantine_commune.csv"

OUT_MASTER = BASE / "orphans_reconciliation_master.csv"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def evidence_rank(value: str) -> int:
    value = (value or "").lower()
    if value == "sha256":
        return 3
    if value == "sha1":
        return 2
    if value == "md5":
        return 1
    return 0


# Load rollup data
rollup = {}
with ROLLUP.open(newline="") as f:
    reader = csv.DictReader(f)
    required = {
        "relative_path",
        "checksum",
        "match_rows",
        "source_count",
        "sources",
        "quarantine_match_rows",
        "commune_match_rows",
        "source_path_count",
        "status",
    }
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"Missing required columns in {ROLLUP}: {sorted(missing)}")
    for row in reader:
        rel = row.get("relative_path")
        if rel:
            rollup[rel] = row

# Load reconciliation rows
recon_rows = []
max_rank_by_rel = {}
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
        if rel not in rollup:
            continue
        rank = evidence_rank(row.get("evidence"))
        max_rank_by_rel[rel] = max(max_rank_by_rel.get(rel, 0), rank)
        recon_rows.append(row)

# Write master reconciliation
with OUT_MASTER.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "relative_path",
        "checksum",
        "status",
        "match_rows",
        "source_count",
        "sources",
        "quarantine_match_rows",
        "commune_match_rows",
        "source_path_count",
        "source",
        "source_path",
        "source_size",
        "source_mtime",
        "evidence",
        "evidence_rank",
        "best_evidence",
    ])

    # Matched rows
    for row in sorted(recon_rows, key=lambda r: (r.get("relative_path") or "", r.get("source") or "", r.get("source_path") or "")):
        rel = row.get("relative_path")
        roll = rollup.get(rel, {})
        rank = evidence_rank(row.get("evidence"))
        best = 1 if rank > 0 and rank == max_rank_by_rel.get(rel, 0) else 0
        writer.writerow([
            rel,
            roll.get("checksum", ""),
            roll.get("status", ""),
            roll.get("match_rows", ""),
            roll.get("source_count", ""),
            roll.get("sources", ""),
            roll.get("quarantine_match_rows", ""),
            roll.get("commune_match_rows", ""),
            roll.get("source_path_count", ""),
            row.get("source", ""),
            row.get("source_path", ""),
            row.get("source_size", ""),
            row.get("source_mtime", ""),
            row.get("evidence", ""),
            rank,
            best,
        ])

    # Unmatched rows (one row per orphan with no evidence)
    for rel in sorted(rollup):
        if rollup[rel].get("status") != "unmatched":
            continue
        roll = rollup[rel]
        writer.writerow([
            rel,
            roll.get("checksum", ""),
            roll.get("status", ""),
            roll.get("match_rows", ""),
            roll.get("source_count", ""),
            roll.get("sources", ""),
            roll.get("quarantine_match_rows", ""),
            roll.get("commune_match_rows", ""),
            roll.get("source_path_count", ""),
            "",
            "",
            "",
            "",
            "",
            0,
            0,
        ])

# Verification output
with OUT_MASTER.open(newline="") as f:
    row_count = sum(1 for _ in csv.reader(f)) - 1
print(f"{OUT_MASTER}\t{row_count}\t{sha256_path(OUT_MASTER)}")
