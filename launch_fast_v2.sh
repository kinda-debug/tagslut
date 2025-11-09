#!/bin/bash

# Fast file deduplication scan using v2 script (avoids SQLite locking)
# Usage: bash launch_fast_v2.sh [/path/to/scan] [/path/to/output]

REPO_DIR="/Users/georgeskhawam/dedupe_repo"
SCAN_DIR="${1:---}/Volumes/dotad/Quarantine"
OUTPUT_FILE="${2:---}/tmp/dupes_quarantine_fast.csv"
LOG_FILE="/tmp/scan_fast_v2.log"

echo "[$(date)] Starting fast scan v2..." > "$LOG_FILE"
echo "Scanning: $SCAN_DIR" >> "$LOG_FILE"
echo "Output: $OUTPUT_FILE" >> "$LOG_FILE"
echo "---" >> "$LOG_FILE"

nohup python3 "$REPO_DIR/scripts/find_dupes_fast_v2.py" "$SCAN_DIR" --output "$OUTPUT_FILE" >> "$LOG_FILE" 2>&1 &

PID=$!
echo "[$(date)] Scan started with PID: $PID" >> "$LOG_FILE"

echo "✓ Fast scan v2 launched"
echo "  PID: $PID"
echo "  Log: tail -f $LOG_FILE"
echo "  Results: $OUTPUT_FILE"
