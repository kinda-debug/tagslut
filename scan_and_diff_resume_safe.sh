#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

# Directories to scan (directory names only; must match DB filenames)
DIRS=(
    "MUSIC"
    "NEW_MUSIC"
    "NEW_LIBRARY"
    "QUARANTINE_AUTO_GLOBAL"
)

# Root volume path
ROOT="/Volumes/dotad"

# SQLite database locations
SCAN_DB_DIR="artifacts/db"
FINAL_DB="${SCAN_DB_DIR}/library_final.db"

# Output lists
OUT_FS_PREFIX="fs"
OUT_DB_PREFIX="db"
OUT_MISSING_PREFIX="missing"

mkdir -p "$SCAN_DB_DIR"

# ------------------------------------------------------------
# 1. RESUME-SAFE SCANS
# ------------------------------------------------------------
for d in "${DIRS[@]}"; do
    ROOT_PATH="${ROOT}/${d}"
    OUT_DB="${SCAN_DB_DIR}/${d}.db"

    echo "------------------------------------------------------------"
    echo "RESUME-SAFE SCAN: ${ROOT_PATH}"
    echo "DB: ${OUT_DB}"
    echo "------------------------------------------------------------"

    python3 - <<EOF
from pathlib import Path
from dedupe.scanner import ScanConfig, scan_library
import logging

logging.basicConfig(level=logging.INFO)

config = ScanConfig(
    root=Path("$ROOT_PATH"),
    database=Path("$OUT_DB"),
    include_fingerprints=False,
    batch_size=100,
    resume=True,
    resume_safe=True,
    show_progress=False,
)

scan_library(config)
EOF

done

# ------------------------------------------------------------
# 2. MERGE INDIVIDUAL DBs INTO FINAL DB
# ------------------------------------------------------------

echo "------------------------------------------------------------"
echo "MERGING INTO ${FINAL_DB}"
echo "------------------------------------------------------------"

rm -f "$FINAL_DB"

sqlite3 "$FINAL_DB" "
CREATE TABLE IF NOT EXISTS library_files(
    path TEXT PRIMARY KEY,
    size_bytes INTEGER,
    mtime REAL,
    checksum TEXT,
    duration REAL,
    sample_rate INTEGER,
    bit_rate INTEGER,
    channels INTEGER,
    bit_depth INTEGER,
    tags_json TEXT,
    fingerprint TEXT,
    fingerprint_duration REAL
);
"

for d in "${DIRS[@]}"; do
    ROOT_DB="${SCAN_DB_DIR}/${d}.db"
    echo "Merging ${ROOT_DB}…"

    sqlite3 "$FINAL_DB" "
        ATTACH '${ROOT_DB}' AS srcdb;
        INSERT OR IGNORE INTO library_files
            SELECT * FROM srcdb.library_files;
        DETACH srcdb;
    "
done

# ------------------------------------------------------------
# 3. BUILD DIFF LISTS (FS vs DB) + FLAC-ONLY LISTS
# ------------------------------------------------------------

echo "------------------------------------------------------------"
echo "BUILDING FILE LISTS"
echo "------------------------------------------------------------"

for d in "${DIRS[@]}"; do
    ROOT_PATH="${ROOT}/${d}"
    FS_LIST="${OUT_FS_PREFIX}_${d}.txt"
    DB_LIST="${OUT_DB_PREFIX}_${d}.txt"
    MISSING_LIST="${OUT_MISSING_PREFIX}_${d}.txt"
    MISSING_FLAC_LIST="${OUT_MISSING_PREFIX}_${d}_flac.txt"

    echo "Building filesystem list: ${FS_LIST}"
    find "$ROOT_PATH" -type f | sort > "$FS_LIST"

    echo "Building DB list: ${DB_LIST}"
    sqlite3 "$FINAL_DB" "
        SELECT path FROM library_files
        WHERE path LIKE '${ROOT_PATH}/%'
        ORDER BY path;
    " > "$DB_LIST"

    echo "Generating missing list: ${MISSING_LIST}"
    comm -23 "$FS_LIST" "$DB_LIST" > "$MISSING_LIST"

    echo "Filtering FLAC-only list: ${MISSING_FLAC_LIST}"
    grep -i '\.flac$' "$MISSING_LIST" > "$MISSING_FLAC_LIST" || true
done

# ------------------------------------------------------------
# 4. BUILD MISSING-ONLY SQLITE DBs (FLAC ONLY)
# ------------------------------------------------------------

echo "------------------------------------------------------------"
echo "BUILDING MISSING-ONLY SQLITE DBs (FLAC ONLY)"
echo "------------------------------------------------------------"

python3 - << 'EOF'
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from dedupe import scanner, utils

DIRS = ["MUSIC", "NEW_MUSIC", "NEW_LIBRARY", "QUARANTINE_AUTO_GLOBAL"]
SCAN_DB_DIR = Path("artifacts/db")
BASE_MISSING_PREFIX = "missing"

def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS library_files(
            path TEXT PRIMARY KEY,
            size_bytes INTEGER,
            mtime REAL,
            checksum TEXT,
            duration REAL,
            sample_rate INTEGER,
            bit_rate INTEGER,
            channels INTEGER,
            bit_depth INTEGER,
            tags_json TEXT,
            fingerprint TEXT,
            fingerprint_duration REAL
        )
        """
    )

for d in DIRS:
    missing_flac = Path(f"{BASE_MISSING_PREFIX}_{d}_flac.txt")
    missing_raw = Path(f"{BASE_MISSING_PREFIX}_{d}.txt")

    if missing_flac.exists():
        candidates = [
            line.strip()
            for line in missing_flac.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    elif missing_raw.exists():
        # Fallback: filter FLAC paths in Python
        candidates = [
            line.strip()
            for line in missing_raw.read_text(encoding="utf-8").splitlines()
            if line.strip().lower().endswith(".flac")
        ]
    else:
        print(f"[SKIP] {d}: no missing list found.")
        continue

    if not candidates:
        print(f"[MISSING-DB] {d}: no FLAC paths, skipping.")
        continue

    out_db = SCAN_DB_DIR / f"{d}_missing.db"
    if out_db.exists():
        out_db.unlink()

    print(f"[MISSING-DB] {d}: {len(candidates)} files -> {out_db}")

    db_ctx = utils.DatabaseContext(out_db)
    with db_ctx.connect() as connection:
        ensure_schema(connection)

        batch: list[scanner.ScanRecord] = []
        processed = 0
        start = time.time()

        for raw_path in candidates:
            p = Path(raw_path)
            if not p.is_file():
                print(f"  [WARN] missing on disk: {p}")
                continue

            try:
                rec = scanner.prepare_record(p, include_fingerprints=False)
            except Exception as exc:
                print(f"  [ERROR] failed to scan {p}: {exc}")
                continue

            batch.append(rec)
            if len(batch) >= 100:
                scanner._upsert_batch(connection, batch)
                connection.commit()
                processed += len(batch)
                batch.clear()

        if batch:
            scanner._upsert_batch(connection, batch)
            connection.commit()
            processed += len(batch)

        elapsed = time.time() - start
        print(f"  [DONE] {d}: wrote {processed} rows in {elapsed:.1f}s")

print("DONE: Missing-only DBs created.")
EOF

# ------------------------------------------------------------
# DONE
# ------------------------------------------------------------

echo "------------------------------------------------------------"
echo "DONE."
echo "Reports generated:"
for d in "${DIRS[@]}"; do
    echo "   ${OUT_MISSING_PREFIX}_${d}.txt"
    echo "   ${OUT_MISSING_PREFIX}_${d}_flac.txt"
done
echo "------------------------------------------------------------"