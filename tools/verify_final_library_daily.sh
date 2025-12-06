#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="$REPO/artifacts/db/library_canonical_fresh.db"
FINAL_ROOT="/Volumes/bad/FINAL_LIBRARY"
OUTDIR="$REPO/artifacts/logs/daily_checks"
mkdir -p "$OUTDIR"

STAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
LOG="$OUTDIR/daily_check_$STAMP.log"

echo "=== DAILY FINAL LIBRARY VERIFICATION ===" | tee "$LOG"
echo "Using canonical DB: $DB" | tee -a "$LOG"
echo "Checking disk root: $FINAL_ROOT" | tee -a "$LOG"
echo | tee -a "$LOG"

if [[ ! -f "$DB" ]]; then
    echo "ERROR: Canonical DB missing: $DB" | tee -a "$LOG"
    exit 1
fi

echo "--- Checking for missing canonical files ---" | tee -a "$LOG"
sqlite3 "$DB" "SELECT path FROM library_files;" | while read -r p; do
    [[ -f "$p" ]] || echo "MISSING: $p" | tee -a "$LOG"
done
echo | tee -a "$LOG"

echo "--- Checking for unexpected files on disk ---" | tee -a "$LOG"
find "$FINAL_ROOT" -type f -name "*.flac" | while read -r p; do
    count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM library_files WHERE path = '$p';")
    [[ "$count" -eq 0 ]] && echo "EXTRA: $p" | tee -a "$LOG"
done
echo | tee -a "$LOG"

echo "--- DONE ---" | tee -a "$LOG"
echo "Log saved to: $LOG"
