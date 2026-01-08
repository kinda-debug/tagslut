#!/usr/bin/env python3
# Proves: derives a deterministic investigation list for unmatched orphans from existing CSV artifacts.
# Does not prove: filesystem existence, provenance, or correctness beyond the input CSV contents.

import csv
import hashlib
import os
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")
UNMATCHED = BASE / "orphans_without_quarantine_or_commune_match.csv"

OUT_LIST = BASE / "orphans_unmatched_investigation_list.csv"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def split_parts(path: str) -> list[str]:
    return [p for p in path.split("/") if p]


rows = []
with UNMATCHED.open(newline="") as f:
    reader = csv.DictReader(f)
    required = {"relative_path", "checksum"}
    missing = required - set(reader.fieldnames or [])
    if missing:
        raise SystemExit(f"Missing required columns in {UNMATCHED}: {sorted(missing)}")
    for row in reader:
        rel = row.get("relative_path") or ""
        checksum = row.get("checksum") or ""
        parts = split_parts(rel)
        depth = len(parts)
        basename = parts[-1] if parts else ""
        dirname = "/".join(parts[:-1]) if len(parts) > 1 else ""
        top_level = parts[0] if len(parts) > 0 else ""
        second_level = parts[1] if len(parts) > 1 else ""
        ext = os.path.splitext(basename)[1].lstrip(".").lower() if basename else ""
        rows.append([
            rel,
            checksum,
            basename,
            dirname,
            depth,
            top_level,
            second_level,
            ext,
        ])

with OUT_LIST.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "relative_path",
        "checksum",
        "basename",
        "dirname",
        "depth",
        "top_level",
        "second_level",
        "extension",
    ])
    for row in sorted(rows, key=lambda r: r[0]):
        writer.writerow(row)

with OUT_LIST.open(newline="") as f:
    row_count = sum(1 for _ in csv.reader(f)) - 1
print(f"{OUT_LIST}\t{row_count}\t{sha256_path(OUT_LIST)}")
