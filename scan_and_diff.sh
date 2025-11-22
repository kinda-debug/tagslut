#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# DIRECTORIES TO SCAN (edit here if needed)
# ------------------------------------------------------------
BASE="/Volumes/dotad"

DIRS=(
  "MUSIC"
  "NEW_MUSIC"
  "NEW_LIBRARY"
  "QUARANTINE_AUTO_GLOBAL"
)

# ------------------------------------------------------------
# DB paths
# ------------------------------------------------------------
FINAL_DB="artifacts/db/library_final.db"
SCAN_DB_DIR="artifacts/db"

mkdir -p "$SCAN_DB_DIR"

# ------------------------------------------------------------
# 1. SCAN EACH DIRECTORY INTO ITS OWN DB
# ------------------------------------------------------------

for d in "${DIRS[@]}"; do
    ROOT="${BASE}/${d}"
    OUT_DB="${SCAN_DB_DIR}/${d}.db"

    echo "------------------------------------------------------------"
    echo "SCANNING: ${ROOT}"
    echo "OUTPUT DB: ${OUT_DB}"
    echo "------------------------------------------------------------"

    rm -f "$OUT_DB"

    python3 - <<EOF
from pathlib import Path
from dedupe.scanner import ScanConfig, scan_library

config = ScanConfig(
    root=Path("${ROOT}"),
    database=Path("${OUT_DB}"),
    include_fingerprints=False,
    batch_size=100,
    resume=False,
    resume_safe=False,
    show_progress=True,
)

scan_library(config)
EOF

done

# ------------------------------------------------------------
# 2. MERGE INDIVIDUAL DBS INTO FINAL
# ------------------------------------------------------------

echo "------------------------------------------------------------"
echo "MERGING INTO ${FINAL_DB}"
echo "------------------------------------------------------------"

rm -f "$FINAL_DB"
sqlite3 "$FINAL_DB" "CREATE TABLE IF NOT EXISTS library_files(
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
);"

for d in "${DIRS[@]}"; do
    ROOT_DB="${SCAN_DB_DIR}/${d}.db"
    echo "Merging $ROOT_DB …"

    sqlite3 "$FINAL_DB" "
    ATTACH '${ROOT_DB}' AS srcdb;
    INSERT OR IGNORE INTO library_files SELECT * FROM srcdb.library_files;
    DETACH srcdb;
    "
done

# ------------------------------------------------------------
# 3. EXTRACT FILESYSTEM AND DB PATHS, SORT THEM
# ------------------------------------------------------------

echo "------------------------------------------------------------"
echo "BUILDING FILE LISTS"
echo "------------------------------------------------------------"

for d in "${DIRS[@]}"; do
    ROOT="${BASE}/${d}"

    FS="fs_${d}.txt"
    DB="db_${d}.txt"
    MISS="missing_${d}.txt"

    echo "Building filesystem list: ${FS}"
    find "$ROOT" -type f -print0 | sort -z | tr '\0' '\n' > "$FS"

    echo "Building DB list: ${DB}"
    sqlite3 "$FINAL_DB" "
      SELECT path FROM library_files
      WHERE path LIKE '${ROOT}/%'
      ORDER BY path;
    " > "$DB"

    echo "Generating missing list: ${MISS}"
    comm -23 "$FS" "$DB" > "$MISS"
done

echo "------------------------------------------------------------"
echo "DONE."
echo "Reports generated:"
for d in "${DIRS[@]}"; do
    echo "   missing_${d}.txt"
done
echo "------------------------------------------------------------"
