#!/usr/bin/env bash
# Pool Validation for Gig 2026-03-13
# Run this AFTER execute completes
# Run this BEFORE importing into Rekordbox

set -euo pipefail

echo "====================================="
echo "Pool Validation: Gig 2026-03-13"
echo "====================================="
echo ""

# Check required env vars
if [ -z "${VOLUME_WORK:-}" ]; then
    echo "ERROR: VOLUME_WORK not set."
    exit 1
fi

GIG_ROOT="${VOLUME_WORK}/gig_runs/gig_2026_03_13"

# Find the most recent timestamped directory
RUN_DIR=$(find "$GIG_ROOT" -maxdepth 1 -type d -name "gig_2026_03_13_*" | sort -r | head -1)

if [ -z "$RUN_DIR" ]; then
    echo "ERROR: No timestamped run directory found in $GIG_ROOT"
    echo "Run 02_execute.sh first."
    exit 1
fi

POOL_DIR="${RUN_DIR}/pool"

if [ ! -d "$POOL_DIR" ]; then
    echo "ERROR: Pool directory not found at $POOL_DIR"
    exit 1
fi

echo "Validating pool: $POOL_DIR"
echo ""

fail_count=0

# Check 1: Zero-byte files
echo "[1/4] Checking for zero-byte files..."
zero_files=$(find "$POOL_DIR" -name "*.mp3" -size 0 2>/dev/null)
if [ -n "$zero_files" ]; then
    echo "ERROR: Found zero-byte files:"
    echo "$zero_files"
    ((fail_count++))
else
    echo "  OK: No zero-byte files"
fi
echo ""

# Check 2: Suspiciously small files
echo "[2/4] Checking for truncated files (< 1MB)..."
small_files=$(find "$POOL_DIR" -name "*.mp3" -size -1M 2>/dev/null)
if [ -n "$small_files" ]; then
    echo "WARNING: Found suspiciously small files:"
    echo "$small_files"
    echo "(These may be valid short tracks or intros - verify manually)"
else
    echo "  OK: No suspiciously small files"
fi
echo ""

# Check 3: Non-MP3 files
echo "[3/4] Checking for non-MP3 files..."
non_mp3=$(find "$POOL_DIR" -type f ! -name "*.mp3" 2>/dev/null)
if [ -n "$non_mp3" ]; then
    echo "WARNING: Found non-MP3 files:"
    echo "$non_mp3"
    echo "(These will not load in Rekordbox)"
else
    echo "  OK: All files are MP3"
fi
echo ""

# Check 4: Total count
echo "[4/4] Counting total files..."
total_mp3=$(find "$POOL_DIR" -name "*.mp3" -type f | wc -l)
echo "  Total MP3 files: $total_mp3"

if [ "$total_mp3" -lt 70 ]; then
    echo "  WARNING: Pool size is small (< 70 tracks)"
elif [ "$total_mp3" -gt 150 ]; then
    echo "  WARNING: Pool size is large (> 150 tracks) - may be hard to navigate"
else
    echo "  OK: Pool size is in recommended range (70-150)"
fi
echo ""

# Summary
echo "====================================="
if [ $fail_count -eq 0 ]; then
    echo "Pool validation PASSED."
    echo ""
    echo "NEXT STEPS:"
    echo "1. Manually spot-check a few files:"
    echo "   - Open 3-5 random tracks and verify they play"
    echo "   - Check filenames are legible"
    echo ""
    echo "2. After manual verification, create:"
    echo "   ${RUN_DIR}/POOL_VERIFIED.txt"
    echo ""
    echo "3. Then import into Rekordbox:"
    echo "   Import ONLY: ${POOL_DIR}"
    echo ""
    echo "Do NOT import until POOL_VERIFIED.txt exists."
else
    echo "Pool validation FAILED with $fail_count critical error(s)."
    echo "Fix issues before importing into Rekordbox."
    exit 1
fi
