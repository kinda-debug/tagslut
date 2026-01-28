#!/usr/bin/env bash
# beatport_harvest_and_import.sh
#
# End-to-end workflow:
#   1) Load env_exports.sh (for BEATPORT_ACCESS_TOKEN, etc.)
#   2) Run dedupe/metadata/beatport_harvest_my_tracks.sh
#      -> writes beatport_my_tracks.ndjson (or a custom OUTPUT)
#   3) Run Python importer dedupe.metadata.beatport_import_my_tracks
#      -> imports NDJSON into SQLite DB
#
# Usage:
#   chmod +x beatport_harvest_and_import.sh
#   ./beatport_harvest_and_import.sh /path/to/music.db
#
# Example:
#   ./beatport_harvest_and_import.sh \
#     /Users/georgeskhawam/Projects/dedupe/EPOCH_2026-01-27/music.db

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

DB_PATH="${1:-}"

if [[ -z "$DB_PATH" ]]; then
  echo "Usage: $0 /path/to/music.db" >&2
  exit 1
fi

if [[ ! -f "$DB_PATH" ]]; then
  echo "ERROR: Database not found: $DB_PATH" >&2
  exit 1
fi

echo "Project root:  $PROJECT_ROOT"
echo "Database path: $DB_PATH"
echo "----------------------------------------"

# 1) Source env_exports.sh
ENV_FILE="${PROJECT_ROOT}/env_exports.sh"

if [[ ! -f "$ENV_FILE" ]]; then
  cat >&2 <<EOF
ERROR: env_exports.sh not found at:
  $ENV_FILE

Create it and set at least:
  export BEATPORT_ACCESS_TOKEN='your-beatport-access-token'

Then re-run this script.
EOF
  exit 1
fi

echo "Sourcing env_exports.sh..."
# shellcheck source=/dev/null
source "$ENV_FILE"

# 2) Check Beatport token
if [[ -z "${BEATPORT_ACCESS_TOKEN:-}" ]]; then
  cat >&2 <<EOF
ERROR: BEATPORT_ACCESS_TOKEN is not set in env_exports.sh.

Add a line like:
  export BEATPORT_ACCESS_TOKEN='your-beatport-access-token'

Then re-run this script.
EOF
  exit 1
fi

# 3) Run the harvester to produce NDJSON
HARVEST_SCRIPT="${PROJECT_ROOT}/dedupe/metadata/beatport_harvest_my_tracks.sh"

if [[ ! -x "$HARVEST_SCRIPT" ]]; then
  echo "Making harvester executable: $HARVEST_SCRIPT"
  chmod +x "$HARVEST_SCRIPT"
fi

echo "----------------------------------------"
echo "Running Beatport harvester..."
echo "  Script: $HARVEST_SCRIPT"
echo

# Let the harvester decide OUTPUT, LOG_FILE, etc. based on env vars.
# Default OUTPUT is beatport_my_tracks.ndjson in PROJECT_ROOT.
( cd "$PROJECT_ROOT" && "$HARVEST_SCRIPT" )

# Determine NDJSON path (honor BEATPORT_MY_TRACKS_NDJSON if set)
NDJSON_PATH="${BEATPORT_MY_TRACKS_NDJSON:-${PROJECT_ROOT}/beatport_my_tracks.ndjson}"

if [[ ! -f "$NDJSON_PATH" ]]; then
  cat >&2 <<EOF
ERROR: Expected NDJSON file not found.

Looked for:
  $NDJSON_PATH

If the harvester wrote to a different path, either:
  - set BEATPORT_MY_TRACKS_NDJSON to that path in env_exports.sh, or
  - adjust NDJSON_PATH in this script.

Check the harvester log (by default beatport_my_tracks.log).
EOF
  exit 1
fi

echo "----------------------------------------"
echo "Harvester complete."
echo "NDJSON file: $NDJSON_PATH"
echo "Preview of first 3 lines:"
head -n 3 "$NDJSON_PATH" || true
echo "----------------------------------------"

# 4) Run the Python importer
echo "Running Python importer..."
echo

cd "$PROJECT_ROOT"
python -m dedupe.metadata.beatport_import_my_tracks \
  --db "$DB_PATH" \
  --input "$NDJSON_PATH"

IMPORT_STATUS=$?

echo "----------------------------------------"
if [[ $IMPORT_STATUS -eq 0 ]]; then
  echo "Import finished successfully."
else
  echo "Import exited with status $IMPORT_STATUS" >&2
fi

exit "$IMPORT_STATUS"
