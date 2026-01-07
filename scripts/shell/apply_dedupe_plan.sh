#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO/scripts/shell/_resolve_db_path.sh"

DB="${DB:-${DEDUPE_DB:-}}"
PLAN_OUT="${PLAN_OUT:-}"

DB="$(require_db_value "$DB" "DB")"
PLAN_OUT="$(require_db_value "$PLAN_OUT" "PLAN_OUT")"
DB="$(resolve_db_path "read" "$DB")"

# Timestamped staging directory
TS=$(date +"%Y%m%d_%H%M%S")
QUAR="/Volumes/COMMUNE/10_STAGING/_DEDUPER_QUARANTINE_$TS"

mkdir -p "$QUAR"

echo "Staging directory:"
echo "  $QUAR"
echo

echo "Extracting dedupe plan from DB…"

# We regenerate the dedupe plan fresh, from DB, to ensure accuracy.
sqlite3 "$DB" <<SQL > "$PLAN_OUT"
SELECT path
FROM library_files
WHERE checksum IN (SELECT checksum FROM canonical)
AND path NOT IN (SELECT path FROM canonical);
SQL

echo "Items in dedupe plan:"
wc -l "$PLAN_OUT"
echo

echo "Moving non-canonical duplicates to staging…"
moved=0
failed=0

while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if [[ -f "$f" ]]; then
        dest="$QUAR/$(basename "$f")"
        mv "$f" "$dest" && moved=$((moved+1)) || failed=$((failed+1))
    else
        echo "Missing file on disk: $f"
        failed=$((failed+1))
    fi

done < "$PLAN_OUT"

echo
echo "=== DEDUPE MOVE COMPLETE ==="
echo "Moved:   $moved"
echo "Failed:  $failed"
echo "Staged into: $QUAR"
echo "Plan file: $PLAN_OUT"
