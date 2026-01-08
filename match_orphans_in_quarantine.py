#!/usr/bin/env python3
# Proves: basename-based matches between missing orphan paths and files under /Volumes/RECOVERY_TARGET/_QUARANTINE.
# Does not prove: file identity, checksum equality, or provenance beyond basename match.

import csv
import hashlib
import os
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")
ORPHANS = BASE / "missing_paths_bucket_orphans_ro_bad_commune_vault.csv"
QUARANTINE_ROOT = Path("/Volumes/RECOVERY_TARGET/_QUARANTINE")

OUT_INVENTORY = BASE / "quarantine_inventory.csv"
OUT_MATCHES = BASE / "orphans_in_quarantine_by_basename.csv"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_orphan_basenames(path: Path):
    basenames = {}
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if "relative_path" not in (reader.fieldnames or []):
            raise SystemExit(f"Missing relative_path column in {path}")
        for row in reader:
            rel = row.get("relative_path")
            if not rel:
                continue
            base = os.path.basename(rel)
            basenames.setdefault(base, set()).add(rel)
    return basenames


def walk_quarantine(root: Path):
    files = []
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            full = Path(dirpath) / name
            try:
                st = full.stat()
            except OSError:
                continue
            files.append((str(full), name, st.st_size, st.st_mtime))
    files.sort(key=lambda x: x[0])
    return files


if not QUARANTINE_ROOT.exists():
    raise SystemExit(f"Quarantine root not found: {QUARANTINE_ROOT}")

orphan_basenames = load_orphan_basenames(ORPHANS)
quarantine_files = walk_quarantine(QUARANTINE_ROOT)

# Write inventory
with OUT_INVENTORY.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["path", "basename", "size", "mtime"])
    for path, base, size, mtime in quarantine_files:
        writer.writerow([path, base, size, mtime])

# Write matches (basename only)
with OUT_MATCHES.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["relative_path", "basename", "quarantine_path", "quarantine_size", "quarantine_mtime"])
    for path, base, size, mtime in quarantine_files:
        if base in orphan_basenames:
            for rel in sorted(orphan_basenames[base]):
                writer.writerow([rel, base, path, size, mtime])

# Verification output
for path in (OUT_INVENTORY, OUT_MATCHES):
    with path.open(newline="") as f:
        row_count = sum(1 for _ in csv.reader(f)) - 1
    print(f"{path}\t{row_count}\t{sha256_path(path)}")
