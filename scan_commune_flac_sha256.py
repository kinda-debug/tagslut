#!/usr/bin/env python3
# Proves: enumerates .flac files under /Volumes/COMMUNE and computes size, mtime, and SHA-256.
# Does not prove: file identity, provenance, or any linkage to DB records.

import csv
import hashlib
import os
from pathlib import Path

BASE = Path("/Users/georgeskhawam/Projects/dedupe")
ROOT = Path("/Volumes/COMMUNE")
OUT = BASE / "commune_flac_sha256.csv"
OUT_ERRORS = BASE / "commune_flac_scan_errors.csv"


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


if not ROOT.exists():
    raise SystemExit(f"Missing root: {ROOT}")

row_count = 0
error_count = 0

with OUT.open("w", newline="") as out_f, OUT_ERRORS.open("w", newline="") as err_f:
    writer = csv.writer(out_f)
    err_writer = csv.writer(err_f)
    writer.writerow(["path", "size", "mtime", "sha256"])
    err_writer.writerow(["path", "error"])

    for root, dirs, files in os.walk(ROOT):
        dirs.sort()
        files.sort()
        for name in files:
            if not name.lower().endswith(".flac"):
                continue
            path = Path(root) / name
            try:
                st = path.stat()
                size = st.st_size
                mtime = st.st_mtime
                digest = file_sha256(path)
                writer.writerow([str(path), size, mtime, digest])
                row_count += 1
            except OSError as exc:
                err_writer.writerow([str(path), str(exc)])
                error_count += 1

print(f"{OUT}\t{row_count}\t{sha256_path(OUT)}")
print(f"{OUT_ERRORS}\t{error_count}\t{sha256_path(OUT_ERRORS)}")
