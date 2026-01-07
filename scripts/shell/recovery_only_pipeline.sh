#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO/scripts/shell/_resolve_db_path.sh"

ROOT=${1:-}
DB=${2:-${DEDUPE_DB:-}}
PLAN=${3:-}

ROOT="$(require_db_value "$ROOT" "ROOT")"
DB="$(require_db_value "$DB" "DB")"
PLAN="$(require_db_value "$PLAN" "PLAN")"
DB="$(resolve_db_path "write" "$DB")"

mkdir -p "$(dirname "$PLAN")"

echo "Scanning recovery library..."
scan_args=(
  python3 tools/integrity/scan.py "$ROOT"
  --db "$DB"
  --library recovery
  --incremental
  --no-check-integrity
  --no-check-hash
  --progress
  --progress-interval 50
  --verbose
)
if [[ -n "${CREATE_DB:-}" ]]; then
  scan_args+=(--create-db)
fi
if [[ -n "${ALLOW_REPO_DB:-}" ]]; then
  scan_args+=(--allow-repo-db)
fi
"${scan_args[@]}"

echo "Generating plan..."
python3 tools/decide/recommend.py --db "$DB" --output "$PLAN"

echo "Dry-run apply (no deletes)..."
python3 tools/decide/apply.py "$PLAN"

echo "Done. Plan written to: $PLAN"
