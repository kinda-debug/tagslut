#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO/scripts/shell/_resolve_db_path.sh"

SCAN_ROOT="${SCAN_ROOT:-}"
DB_OUT="${DB_OUT:-}"
LOG="${LOG:-$REPO/artifacts/logs/scan_final_library.log}"
SUMMARY="${SUMMARY:-$REPO/artifacts/logs/scan_final_library_summary.txt}"
PY_SCAN="$REPO/scripts/python/scan_final_library.py"

SCAN_ROOT="$(require_db_value "$SCAN_ROOT" "SCAN_ROOT")"
DB_OUT="$(require_db_value "$DB_OUT" "DB_OUT")"
if [[ -z "${CREATE_DB:-}" ]]; then
    echo "Error: set CREATE_DB=1 to allow DB creation." >&2
    exit 1
fi
DB_OUT="$(resolve_db_path "write" "$DB_OUT")"

# Activate Python environment if needed (edit if you use a specific venv)
if [[ -f "$REPO/.venv/bin/activate" ]]; then
    source "$REPO/.venv/bin/activate"
elif [[ -f "$REPO/venv/bin/activate" ]]; then
    source "$REPO/venv/bin/activate"
fi

mkdir -p "$(dirname "$LOG")"
mkdir -p "$(dirname "$SUMMARY")"
mkdir -p "$(dirname "$LOG")"

# Remove previous DB if present
if [[ -f "$DB_OUT" ]]; then
    mv "$DB_OUT" "$DB_OUT.bak.$(date +%Y%m%d_%H%M%S)"
fi

python3 "$PY_SCAN" --scan-root "$SCAN_ROOT" --db "$DB_OUT" --create-db | tee "$LOG"

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
