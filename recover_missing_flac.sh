#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n'

MISSING_LIST="all_missing_flac.txt"
DEST_ROOT="/Volumes/dotad/RECOVERED_FROM_MISSING"
LOG="recovery.log"
ERR="recovery_errors.log"

mkdir -p "$DEST_ROOT"
rm -f "$LOG" "$ERR"
touch "$LOG" "$ERR"

echo "------------------------------------------------------------"
echo "RECOVERY STARTED"
echo "Source list: $MISSING_LIST"
echo "Destination: $DEST_ROOT"
echo "Log: $LOG"
echo "Errors: $ERR"
echo "------------------------------------------------------------"

count=0
total=$(wc -l < "$MISSING_LIST" | tr -d ' ')

while IFS= read -r raw_path; do
    # Skip empty lines
    [[ -z "$raw_path" ]] && continue

    # Normalize Unicode (macOS filesystem quirk)
    path=$(printf '%s' "$raw_path" | iconv -f UTF-8 -t UTF-8 -c)

    # Validate existence
    if [[ ! -f "$path" ]]; then
        echo "[MISSING] $path" >> "$ERR"
        continue
    fi

    # Rebuild directory structure inside the recovery folder
    rel="${path#/Volumes/dotad/}"
    dest="$DEST_ROOT/$rel"

    mkdir -p "$(dirname "$dest")"

    # Copy safely (preserves attributes, errors logged)
    if cp -p "$path" "$dest" 2>>"$ERR"; then
        echo "[OK] $path → $dest" >> "$LOG"
    else
        echo "[ERROR] $path" >> "$ERR"
    fi

    count=$((count+1))
    # Status output every 200 files
    if (( count % 200 == 0 )); then
        echo "Processed: $count / $total"
    fi
done < "$MISSING_LIST"

echo "------------------------------------------------------------"
echo "RECOVERY FINISHED"
echo "Copied: $count files"
echo "Log details in: $LOG"
echo "Errors in: $ERR"
echo "Destination root: $DEST_ROOT"
echo "------------------------------------------------------------"
