#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
    echo "Usage: $0 <FS_ROOT> <DB_PATH> <OUT_PREFIX>"
    echo "Example: ./dump_fs_and_db.sh /Volumes/sad/MUSIC artifacts/db/SAD_MUSIC.db artifacts/db/SAD_MUSIC"
    exit 1
fi

FS_ROOT="$1"
DB_PATH="$2"
OUT_PREFIX="$3"

OUT_DIR="$(dirname "$OUT_PREFIX")"
mkdir -p "$OUT_DIR"

RAW_FS="$OUT_PREFIX.fs_raw.txt"
NORM_FS="$OUT_PREFIX.fs.txt"
DB_TSV="$OUT_PREFIX.db.tsv"
DB_PATHS="$OUT_PREFIX.db_paths.txt"
MISSING_IN_FS="$OUT_PREFIX.missing_in_fs.txt"
MISSING_IN_DB="$OUT_PREFIX.missing_in_db.txt"

echo "------------------------------------------------------------"
echo "FS + DB DUMP"
echo "FS root: $FS_ROOT"
echo "DB:      $DB_PATH"
echo "Out:     $OUT_PREFIX.*"
echo "------------------------------------------------------------"

# 1. Scan filesystem for FLAC files
echo "[1/5] Scanning filesystem…"
find "$FS_ROOT" -type f \( -iname "*.flac" \) | sort > "$RAW_FS"

# Normalise paths with Python (using dedupe.utils)
echo "[2/5] Normalising filesystem paths…"
python3 - <<EOF > "$NORM_FS"
import sys
from pathlib import Path
from dedupe.utils import normalise_path

for line in Path("$RAW_FS").read_text().splitlines():
    print(normalise_path(line))
EOF

sort -u "$NORM_FS" -o "$NORM_FS"

# 2. Dump DB to TSV
echo "[3/5] Exporting DB rows…"
sqlite3 "$DB_PATH" -header -separator $'\t' "SELECT * FROM library_files;" > "$DB_TSV"

# 3. Extract DB paths (normalised)
echo "[4/5] Exporting DB paths…"
python3 - <<EOF > "$DB_PATHS"
import sqlite3
from dedupe.utils import normalise_path

conn = sqlite3.connect("$DB_PATH")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT path FROM library_files").fetchall()
for r in rows:
    print(normalise_path(r["path"]))
EOF

sort -u "$DB_PATHS" -o "$DB_PATHS"

# 4. Diff comparisons
echo "[5/5] Computing diffs…"

# Paths in DB but not in FS
comm -23 "$DB_PATHS" "$NORM_FS" > "$MISSING_IN_FS"

# Paths in FS but not in DB
comm -13 "$DB_PATHS" "$NORM_FS" > "$MISSING_IN_DB"

echo "------------------------------------------------------------"
echo "DONE."
echo "Raw FS list:          $RAW_FS"
echo "Normalised FS list:   $NORM_FS"
echo "DB TSV export:        $DB_TSV"
echo "DB paths:             $DB_PATHS"
echo "Missing in FS:        $MISSING_IN_FS"
echo "Missing in DB:        $MISSING_IN_DB"
echo "------------------------------------------------------------"
