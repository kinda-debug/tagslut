#!/usr/bin/env bash
set -euo pipefail

ROOT=${1:-/Volumes/COMMUNE/20_ACCEPTED}
DB=${2:-artifacts/db/music.db}
PLAN=${3:-artifacts/tmp/plan.json}

mkdir -p "$(dirname "$DB")" "$(dirname "$PLAN")"

echo "Scanning recovery library..."
python3 tools/integrity/scan.py "$ROOT" \
  --db "$DB" \
  --library recovery \
  --incremental \
  --no-check-integrity \
  --no-check-hash \
  --progress \
  --progress-interval 50 \
  --verbose

echo "Generating plan..."
python3 tools/decide/recommend.py --db "$DB" --output "$PLAN"

echo "Dry-run apply (no deletes)..."
python3 tools/decide/apply.py "$PLAN"

echo "Done. Plan written to: $PLAN"
