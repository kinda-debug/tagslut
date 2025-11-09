#!/bin/bash
# Launcher for fast deduplication scan
# Runs in proper background with nohup and output redirection

set -e

SCRIPT="scripts/find_dupes_fast.py"
OUTPUT="/tmp/dupes_quarantine_fast.csv"
LOG="/tmp/scan_fast.log"
DB="$HOME/.cache/file_dupes.db"

echo "🚀 Starting Fast File-MD5 Deduplication Scan"
echo "=============================================="
echo ""
echo "Script:  $SCRIPT"
echo "Output:  $OUTPUT"
echo "Log:     $LOG"
echo "DB:      $DB"
echo ""

# Clean previous run
rm -f "$OUTPUT" "$LOG"

# Start in background with nohup
nohup python3 "$SCRIPT" /Volumes/dotad/Quarantine \
    --output "$OUTPUT" \
    --verbose \
    > "$LOG" 2>&1 &

PID=$!
echo "✓ Process started with PID: $PID"
echo ""
echo "Monitor progress:"
echo "  tail -f $LOG"
echo ""
echo "Check status:"
echo "  ps -p $PID"
echo ""
echo "View results when done:"
echo "  head -20 $OUTPUT"
