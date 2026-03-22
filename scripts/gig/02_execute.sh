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
set +e
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
set -e

mapfile -t RUN_DIR_MATCHES < <(sed -n 's/^Run directory: //p' "$RUN_LOG")
parse_error=0
RUN_DIR=""

if [ "${#RUN_DIR_MATCHES[@]}" -eq 0 ]; then
    echo "ERROR: Expected exactly one 'Run directory:' line in execute log, found 0."
    parse_error=1
elif [ "${#RUN_DIR_MATCHES[@]}" -gt 1 ]; then
    echo "ERROR: Expected exactly one 'Run directory:' line in execute log, found ${#RUN_DIR_MATCHES[@]}."
    printf 'Matches:\n'
    printf '  %s\n' "${RUN_DIR_MATCHES[@]}"
    parse_error=1
else
    RUN_DIR_RAW="${RUN_DIR_MATCHES[0]}"
    RUN_DIR="$(cd "$RUN_DIR_RAW" 2>/dev/null && pwd -P || true)"
    if [ -z "$RUN_DIR" ] || [ ! -d "$RUN_DIR" ]; then
        echo "ERROR: Parsed run directory is not accessible: $RUN_DIR_RAW"
        parse_error=1
    fi
fi

echo ""
echo "====================================="
if [ $exec_exit -eq 0 ] && [ $parse_error -eq 0 ]; then
    echo "Execute completed. Checking results..."
    echo ""

    echo "Resolved execute run directory: $RUN_DIR"
    echo ""
    
    # Count files
    POOL_DIR="${RUN_DIR}/pool"
    if [ -d "$POOL_DIR" ]; then
        FILE_COUNT=$(find "$POOL_DIR" -name "*.mp3" -type f | wc -l)
        echo "Files in pool: $FILE_COUNT"
        echo ""
        echo "NEXT STEPS:"
        echo "1. Run 03_validate_pool.sh against this exact run:"
        echo "   bash scripts/gig/03_validate_pool.sh \"$RUN_DIR\""
        echo "2. After validation passes, manually create:"
        echo "   ${RUN_DIR}/POOL_VERIFIED.txt"
        echo "3. Import ${POOL_DIR} into Rekordbox"
    else
        echo "WARNING: pool directory not found at $POOL_DIR"
        exit 1
    fi
else
    if [ $exec_exit -ne 0 ]; then
        echo "Execute FAILED. Check $RUN_LOG for details."
    fi
    if [ $parse_error -ne 0 ]; then
        echo "Run directory parsing FAILED. Fix this before continuing."
    fi
    exit 1
fi
