#!/bin/bash
# Launcher for audio-MD5 deduplication scan
# Runs in proper background with nohup and output redirection

set -e

SCRIPT="scripts/find_exact_dupes.py"
OUTPUT="/tmp/dupes_quarantine_audio.csv"
LOG="/tmp/scan_audio.log"
DB="$HOME/.cache/exact_dupes.db"

echo "🎵 Starting Audio-MD5 Deduplication Scan"
echo "=========================================="
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
