#!/bin/bash

# ==============================
# CONFIGURATION
# ==============================
CANON_DB="artifacts/db/library_canonical.db"
RESCAN_DIR="/tmp/rescan_fix_all"
RESCAN_DB="artifacts/db/tmp_rescan_all.sqlite"

# ==============================
# PREP
# ==============================
rm -rf "$RESCAN_DIR"
mkdir -p "$RESCAN_DIR"

echo "Finding all files with missing metadata…"

# Extract paths with empty extra_json
sqlite3 "$CANON_DB" "
SELECT path 
FROM library_files
WHERE extra_json IS NULL
   OR extra_json = ''
;" > /tmp/missing_metadata_paths.txt

COUNT=$(wc -l < /tmp/missing_metadata_paths.txt)

echo
echo "Found $COUNT files with missing metadata."
echo

# ==============================
# COPY FILES FOR RESCAN
# ==============================
echo "Copying files into: $RESCAN_DIR"
echo

COPIED=0
FAILED=0

while IFS= read -r FILEPATH; do
    if [ -f "$FILEPATH" ]; then
        cp "$FILEPATH" "$RESCAN_DIR/"
        COPIED=$((COPIED+1))
    else
        echo "WARNING: Missing on disk: $FILEPATH"
        FAILED=$((FAILED+1))
    fi
done < /tmp/missing_metadata_paths.txt

echo
echo "Copied: $COPIED"
echo "Missing: $FAILED"
echo

# ==============================
# RESCAN FILES
# ==============================
echo "Running metadata rescan…"
rm -f "$RESCAN_DB"

python3 -m dedupe.cli scan-library \
    --root "$RESCAN_DIR" \
    --out "$RESCAN_DB" \
    --progress

echo
echo "Rescan complete."
echo

# ==============================
# MERGE BACK INTO CANONICAL DB
# ==============================
echo "Merging fixed metadata into canonical database…"

sqlite3 "$CANON_DB" <<SQL
ATTACH '$RESCAN_DB' AS scan;

INSERT OR REPLACE INTO library_files (path, tags_json, extra_json)
SELECT path, tags_json, extra_json
FROM scan.library_files;

DETACH scan;
SQL

echo "Merge complete."

# ==============================
# SUMMARY
# ==============================
echo
echo "====================================="
echo " FIX SUMMARY"
echo "====================================="
echo "Files needing fix:     $COUNT"
echo "Copied for rescan:     $COPIED"
echo "Missing on disk:       $FAILED"
echo "Rescan DB generated at: $RESCAN_DB"
echo "All updated in:        $CANON_DB"
echo "====================================="
echo
echo "Done."
