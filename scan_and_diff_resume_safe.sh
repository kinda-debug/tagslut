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

config = ScanConfig(
    root=Path("$ROOT_PATH"),
    database=Path("$OUT_DB"),
    include_fingerprints=False,
    batch_size=100,
    resume=True,
    resume_safe=True,
    show_progress=True,
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
# 3. BUILD DIFF LISTS
# ------------------------------------------------------------

echo "------------------------------------------------------------"
echo "BUILDING FILE LISTS"
echo "------------------------------------------------------------"

for d in "${DIRS[@]}"; do
    ROOT_PATH="${ROOT}/${d}"
    FS_LIST="${OUT_FS_PREFIX}_${d}.txt"
    DB_LIST="${OUT_DB_PREFIX}_${d}.txt"
    MISSING_LIST="${OUT_MISSING_PREFIX}_${d}.txt"

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
done


# ------------------------------------------------------------
# DONE
# ------------------------------------------------------------

echo "------------------------------------------------------------"
echo "DONE."
echo "Reports generated:"
for d in "${DIRS[@]}"; do
    echo "   ${OUT_MISSING_PREFIX}_${d}.txt"
done
echo "------------------------------------------------------------"