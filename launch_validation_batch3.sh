#!/bin/bash
# Launcher for validation script
# Runs Batch 3 validation (Repaire_dupes)

set -e

SCRIPT="scripts/validate_repair_with_acoustid.py"
INPUT_DIR="/Volumes/dotad/Repaire_dupes"
OUTPUT="/tmp/validate_Repaire_dupes.csv"
LOG="/tmp/validate_batch_3.log"

echo "✓ Starting Batch 3 Validation (Repaire_dupes)"
echo "=============================================="
echo ""
echo "Script:   $SCRIPT"
echo "Input:    $INPUT_DIR"
echo "Output:   $OUTPUT"
echo "Log:      $LOG"
echo ""

# Clean previous run
rm -f "$OUTPUT" "$LOG"

# Start in background with nohup
nohup python3 "$SCRIPT" "$INPUT_DIR" \
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
