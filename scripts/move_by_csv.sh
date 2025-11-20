#!/usr/bin/env bash
set -euo pipefail

CSV="$1"
DEST="$2"

echo "=== MOVE BY CSV (SAFE MODE) ==="
echo "Decisions:   $CSV"
echo "Quarantine:  $DEST"
echo

moved=0
skipped=0
missing=0

# Skip header row (NR>1)
tail -n +2 "$CSV" | \
while IFS= read -r line; do
    # Extract path, action, reason using a safe CSV parser (awk)
    # Fields are quoted, so use FPAT to match CSV quoted fields correctly
    parsed=$(awk -v FPAT='([^,]*)|("[^"]*")' '{ 
        for (i=1;i<=NF;i++) {
            gsub(/^"|"$/, "", $i); 
            printf "%s", $i;
            if (i<NF) printf "\t";
        }
    }' <<< "$line")

    path=$(echo "$parsed" | cut -f1)
    action=$(echo "$parsed" | cut -f2)
    reason=$(echo "$parsed" | cut -f3)

    # If action is not MOVE, skip it
    if [[ "$action" != "MOVE" ]]; then
        ((skipped++))
        continue
    fi

    # Check if file exists
    if [[ ! -f "$path" ]]; then
        ((missing++))
        echo "Missing: $path"
        continue
    fi

    # Ensure destination directory exists
    mkdir -p "$DEST"

    mv -n "$path" "$DEST"/
    ((moved++))

done

echo
echo "=== SUMMARY ==="
echo "Moved files:   $moved"
echo "Skipped rows:  $skipped"
echo "Missing files: $missing"
echo "================"