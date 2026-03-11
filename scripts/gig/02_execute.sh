#!/usr/bin/env bash
# Execute Mode for Gig 2026-03-13
# Run this AFTER plan mode has been validated
# This will copy files - there is no undo

set -euo pipefail

echo "====================================="
echo "Execute Mode: Gig 2026-03-13"
echo "====================================="
echo ""

# Check required env vars
if [ -z "${TAGSLUT_DB:-}" ] || [ -z "${MASTER_LIBRARY:-}" ] || [ -z "${VOLUME_WORK:-}" ]; then
    echo "ERROR: Required environment variables not set."
    echo "Run 00_verify_environment.sh first."
    exit 1
fi

# Set paths
GIG_ROOT="${VOLUME_WORK}/gig_runs/gig_2026_03_13"
PROFILE="${GIG_ROOT}/profile.json"
RUN_LOG="${GIG_ROOT}/run.log"
DJ_CACHE="${DJ_LIBRARY:-$VOLUME_WORK/dj_cache}"

# Check profile exists
if [ ! -f "$PROFILE" ]; then
    echo "ERROR: profile.json not found at $PROFILE"
    exit 1
fi

echo "WARNING: This will execute file copying operations."
echo "There is no undo. Ensure plan mode output was validated."
echo ""
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Using profile: $PROFILE"
echo "Output root: $GIG_ROOT"
echo "Log file: $RUN_LOG"
echo ""
echo "Starting execute mode..."
echo ""

# Run execute with logging
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_CACHE" \
  --out-root "$GIG_ROOT" \
  --execute \
  --non-interactive \
  --profile "$PROFILE" \
  2>&1 | tee "$RUN_LOG"

exec_exit=${PIPESTATUS[0]}

echo ""
echo "====================================="
if [ $exec_exit -eq 0 ]; then
    echo "Execute completed. Checking results..."
    echo ""
    
    # Find the timestamped directory
    RUN_DIR=$(find "$GIG_ROOT" -maxdepth 1 -type d -name "gig_2026_03_13_*" | sort -r | head -1)
    
    if [ -z "$RUN_DIR" ]; then
        echo "ERROR: Could not find timestamped run directory"
        exit 1
    fi
    
    echo "Run directory: $RUN_DIR"
    echo ""
    
    # Count files
    POOL_DIR="${RUN_DIR}/pool"
    if [ -d "$POOL_DIR" ]; then
        FILE_COUNT=$(find "$POOL_DIR" -name "*.mp3" -type f | wc -l)
        echo "Files in pool: $FILE_COUNT"
        echo ""
        echo "NEXT STEPS:"
        echo "1. Run 03_validate_pool.sh to check file integrity"
        echo "2. After validation passes, manually create:"
        echo "   ${RUN_DIR}/POOL_VERIFIED.txt"
        echo "3. Import ${POOL_DIR} into Rekordbox"
    else
        echo "WARNING: pool directory not found at $POOL_DIR"
        exit 1
    fi
else
    echo "Execute FAILED. Check $RUN_LOG for details."
    exit 1
fi
