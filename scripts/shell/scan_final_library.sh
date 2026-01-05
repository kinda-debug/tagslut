#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCAN_ROOT="/Volumes/COMMUNE/20_ACCEPTED"
DB_OUT="$REPO/artifacts/db/library_canonical_fresh.db"
LOG="$REPO/artifacts/logs/scan_final_library.log"
SUMMARY="$REPO/artifacts/logs/scan_final_library_summary.txt"
PY_SCAN="$REPO/scripts/python/scan_final_library.py"

# Activate Python environment if needed (edit if you use a specific venv)
if [[ -f "$REPO/.venv/bin/activate" ]]; then
    source "$REPO/.venv/bin/activate"
elif [[ -f "$REPO/venv/bin/activate" ]]; then
    source "$REPO/venv/bin/activate"
fi

mkdir -p "$(dirname "$DB_OUT")"
mkdir -p "$(dirname "$LOG")"

# Remove previous DB if present
if [[ -f "$DB_OUT" ]]; then
    mv "$DB_OUT" "$DB_OUT.bak.$(date +%Y%m%d_%H%M%S)"
fi

export SCAN_ROOT="$SCAN_ROOT"
export DB_OUT="$DB_OUT"

python3 "$PY_SCAN" | tee "$LOG"

COUNT=$(sqlite3 "$DB_OUT" "SELECT COUNT(*) FROM library_files;")
echo "Total FLAC files scanned: $COUNT" | tee "$SUMMARY"

# Validate file count matches disk
DISK_COUNT=$(find "$SCAN_ROOT" -type f -name "*.flac" | wc -l)
echo "Total FLAC files on disk: $DISK_COUNT" | tee -a "$SUMMARY"

if [[ "$COUNT" -eq "$DISK_COUNT" ]]; then
    echo "✔ All files indexed correctly." | tee -a "$SUMMARY"
else
    echo "✗ Mismatch between DB and disk count!" | tee -a "$SUMMARY"
fi

echo "Scan complete. DB: $DB_OUT" | tee -a "$SUMMARY"
echo "Log: $LOG" | tee -a "$SUMMARY"
