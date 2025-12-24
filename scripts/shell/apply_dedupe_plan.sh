#!/usr/bin/env bash
set -euo pipefail

REPO="$HOME/dedupe_repo_reclone"
DB="$REPO/artifacts/db/library_final.db"

# Timestamped quarantine directory
TS=$(date +"%Y%m%d_%H%M%S")
QUAR="/Volumes/dotad/DEDUPER_QUARANTINE_$TS"

mkdir -p "$QUAR"

echo "Quarantine directory:"
echo "  $QUAR"
echo

echo "Extracting dedupe plan from DB…"

# We regenerate the dedupe plan fresh, from DB, to ensure accuracy.
sqlite3 "$DB" <<SQL > "$REPO/artifacts/db/dedupe_plan.txt"
SELECT path
FROM library_files
WHERE checksum IN (SELECT checksum FROM canonical)
AND path NOT IN (SELECT path FROM canonical);
SQL

echo "Items in dedupe plan:"
wc -l "$REPO/artifacts/db/dedupe_plan.txt"
echo

echo "Moving non-canonical duplicates to quarantine…"
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

done < "$REPO/artifacts/db/dedupe_plan.txt"

echo
echo "=== DEDUPE MOVE COMPLETE ==="
echo "Moved:   $moved"
echo "Failed:  $failed"
echo "Quarantined into: $QUAR"
echo "Plan file: $REPO/artifacts/db/dedupe_plan.txt"
