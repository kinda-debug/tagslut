#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/scripts/shell/_resolve_db_path.sh"
VENVDIR="$REPO/.venv"
FINAL_ROOT="${FINAL_ROOT:-}"
OUTDB="${OUTDB:-}"
REPORT="${REPORT:-$REPO/artifacts/logs/library_canonical_fresh_report.txt}"

FINAL_ROOT="$(require_db_value "$FINAL_ROOT" "FINAL_ROOT")"
OUTDB="$(require_db_value "$OUTDB" "OUTDB")"
if [[ -z "${CREATE_DB:-}" ]]; then
    echo "Error: set CREATE_DB=1 to allow DB creation." >&2
    exit 1
fi
OUTDB="$(resolve_db_path "write" "$OUTDB")"

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
scan_args=(
    /usr/bin/python3 -m dedupe.cli scan-library
    --root "$FINAL_ROOT"
    --db "$OUTDB"
    --progress
    --create-db
)
if [[ -n "${ALLOW_REPO_DB:-}" ]]; then
    scan_args+=(--allow-repo-db)
fi
"${scan_args[@]}"

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
