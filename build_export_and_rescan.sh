#!/usr/bin/env bash
set -euo pipefail

############################################
# CONFIGURATION
############################################
REPO="$HOME/dedupe_repo_reclone"
FINAL_DB="$REPO/artifacts/db/library_final.db"
EXPORT_ROOT="/Volumes/dotad"
TS="$(date +%Y%m%d_%H%M%S)"
EXPORT_DIR="$EXPORT_ROOT/LIBRARY_EXPORT_$TS"
EXPORT_DB="$REPO/artifacts/db/library_export_final.sqlite"
TMP_EXPORT_DB="$EXPORT_DB.tmp"
SCAN_LOG="$REPO/artifacts/db/export_rescan_$TS.log"

############################################
echo "=== EXPORT + RESCAN PIPELINE START ==="
############################################
echo "Timestamp: $TS"
echo "Export directory: $EXPORT_DIR"
echo

############################################
# 1. VERIFY FINAL DB EXISTS
############################################
if [[ ! -f "$FINAL_DB" ]]; then
    echo "ERROR: Missing final DB at $FINAL_DB"
    exit 1
fi

############################################
# 2. CREATE EXPORT DIRECTORY
############################################
echo "=== CREATING CLEAN EXPORT FOLDER ==="
mkdir -p "$EXPORT_DIR"

############################################
# 3. EXPORT CANONICAL FILES FROM FINAL DB
############################################
echo "=== EXPORTING FILES FROM FINAL DB ==="

# Full file list
TMP_LIST="/tmp/export_paths_$TS.txt"
sqlite3 "$FINAL_DB" "SELECT path FROM library_files;" > "$TMP_LIST"

total=$(wc -l < "$TMP_LIST" | tr -d ' ')
echo "Files to export: $total"
echo

copied=0
failed=0

while IFS= read -r src; do
    [[ -f "$src" ]] || { ((failed++)); echo "MISSING FILE: $src"; continue; }

    rel="${src#/Volumes/dotad/}"
    dest="$EXPORT_DIR/$rel"
    mkdir -p "$(dirname "$dest")"

    if cp -p "$src" "$dest" 2>/dev/null; then
        ((copied++))
    else
        ((failed++))
        echo "COPY FAILED: $src"
    fi
done < "$TMP_LIST"

echo
echo "Copied: $copied"
echo "Failed: $failed"
echo

############################################
# 4. RESCAN EXPORTED LIBRARY
############################################
echo "=== SCANNING CLEAN EXPORT DIRECTORY ==="

source "$REPO/.venv/bin/activate"

python3 -m dedupe.cli scan-library \
    --root "$EXPORT_DIR" \
    --out "$TMP_EXPORT_DB" \
    --progress 2>&1 | tee "$SCAN_LOG"

echo

############################################
# 5. FINALIZE EXPORT DB
############################################
echo "=== FINALIZING EXPORT DB ==="
mv "$TMP_EXPORT_DB" "$EXPORT_DB"

rows=$(sqlite3 "$EXPORT_DB" "SELECT COUNT(*) FROM library_files;")
echo "Final export DB rows: $rows"

############################################
# DONE
############################################
echo
echo "=== EXPORT + RESCAN COMPLETE ==="
echo "Export directory: $EXPORT_DIR"
echo "Final export scan DB: $EXPORT_DB"
echo "Scan log: $SCAN_LOG"
