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

# Run plan mode
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_CACHE" \
  --out-root "$GIG_ROOT" \
  --non-interactive \
  --profile "$PROFILE"

plan_exit=$?

echo ""
echo "====================================="
if [ $plan_exit -eq 0 ]; then
    echo "Plan mode completed successfully."
    echo ""
    echo "NEXT STEPS:"
    echo "1. Inspect the generated artifacts in the timestamped directory:"
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
    echo "Plan mode FAILED. Check output above."
    echo "Do NOT proceed to execute until plan mode succeeds."
    exit 1
fi
