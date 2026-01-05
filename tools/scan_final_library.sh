#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENVDIR="$REPO/.venv"
FINAL_ROOT="/Volumes/COMMUNE/20_ACCEPTED"
OUTDB="$REPO/artifacts/db/library_canonical_fresh.db"
REPORT="$REPO/artifacts/logs/library_canonical_fresh_report.txt"

mkdir -p "$REPO/artifacts/db"
mkdir -p "$REPO/artifacts/logs"

echo "=== SCAN FINAL LIBRARY: REBUILD AUTHORITATIVE DB ==="
echo "Source: $FINAL_ROOT"
echo "Output DB: $OUTDB"
echo

if [[ ! -d "$FINAL_ROOT" ]]; then
    echo "ERROR: Final library directory not found: $FINAL_ROOT"
    exit 1
fi

echo "=== Activating environment ==="
source "$VENVDIR/bin/activate"

echo "=== Running scanner ==="
/usr/bin/python3 -m dedupe.cli scan-library \
    --root "$FINAL_ROOT" \
    --out "$OUTDB" \
    --progress

echo
echo "=== Summary report ===" > "$REPORT"

echo "- Total files scanned:" | tee -a "$REPORT"
sqlite3 "$OUTDB" "SELECT COUNT(*) FROM library_files;" | tee -a "$REPORT"
echo >> "$REPORT"

echo "- Missing extra_json entries:" | tee -a "$REPORT"
sqlite3 "$OUTDB" "SELECT COUNT(*) FROM library_files WHERE extra_json IS NULL OR extra_json = '';" | tee -a "$REPORT"
echo >> "$REPORT"

echo "- Duplicate checksum groups:" | tee -a "$REPORT"
sqlite3 "$OUTDB" "
    SELECT COUNT(*)
    FROM (
        SELECT checksum
        FROM library_files
        GROUP BY checksum
        HAVING COUNT(*) > 1
    );
" | tee -a "$REPORT"
echo >> "$REPORT"

echo "=== DONE ==="
echo "Fresh canonical DB: $OUTDB"
echo "Summary report: $REPORT"
