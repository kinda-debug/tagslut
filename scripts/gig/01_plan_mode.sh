#!/usr/bin/env bash
# Plan Mode for Gig 2026-03-13
# Run this AFTER environment verification and profile creation
# Run this BEFORE execute

set -euo pipefail

echo "====================================="
echo "Plan Mode: Gig 2026-03-13"
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
DJ_CACHE="${DJ_LIBRARY:-$VOLUME_WORK/dj_cache}"

# Check profile exists
if [ ! -f "$PROFILE" ]; then
    echo "ERROR: profile.json not found at $PROFILE"
    echo "Create it from docs/gig/templates/profile_initial.json first."
    exit 1
fi

echo "Using profile: $PROFILE"
echo "Output root: $GIG_ROOT"
echo ""
echo "Starting plan mode (dry run)..."
echo ""

TMP_OUTPUT=$(mktemp)
trap 'rm -f "$TMP_OUTPUT"' EXIT

# Run plan mode
set +e
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_CACHE" \
  --out-root "$GIG_ROOT" \
  --non-interactive \
  --profile "$PROFILE" \
  2>&1 | tee "$TMP_OUTPUT"
plan_exit=${PIPESTATUS[0]}
set -e

mapfile -t RUN_DIR_MATCHES < <(sed -n 's/^Run directory: //p' "$TMP_OUTPUT")
parse_error=0
RUN_DIR=""

if [ "${#RUN_DIR_MATCHES[@]}" -eq 0 ]; then
    echo "ERROR: Expected exactly one 'Run directory:' line in plan output, found 0."
    parse_error=1
elif [ "${#RUN_DIR_MATCHES[@]}" -gt 1 ]; then
    echo "ERROR: Expected exactly one 'Run directory:' line in plan output, found ${#RUN_DIR_MATCHES[@]}."
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
if [ $plan_exit -eq 0 ] && [ $parse_error -eq 0 ]; then
    echo "Plan mode completed successfully."
    echo "Resolved plan run directory: $RUN_DIR"
    echo ""
    echo "NEXT STEPS:"
    echo "1. Inspect the generated artifacts in this timestamped directory:"
    echo "   $RUN_DIR"
    echo "   - cohort_health.json"
    echo "   - selected.csv"
    echo "   - plan.csv"
    echo "   - pool_manifest.json"
    echo ""
    echo "2. Verify:"
    echo "   - Selected count is sufficient (90-150 tracks)"
    echo "   - Role/genre distribution supports all five intent layers"
    echo "   - No suspicious cache_action or pool_action entries"
    echo "   - Filenames and layout are legible"
    echo ""
    echo "3. If pool needs tightening:"
    echo "   - Edit profile.json (one axis at a time)"
    echo "   - Rerun this script"
    echo ""
    echo "4. When ready:"
    echo "   - Run 02_execute.sh"
else
    if [ $plan_exit -ne 0 ]; then
        echo "Plan mode FAILED. Check output above."
    fi
    if [ $parse_error -ne 0 ]; then
        echo "Run directory parsing FAILED. Fix this before continuing."
    fi
    echo "Do NOT proceed to execute until plan mode succeeds."
    exit 1
fi
