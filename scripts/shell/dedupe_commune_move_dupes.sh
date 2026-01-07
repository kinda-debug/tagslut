#!/usr/bin/env bash
set -euo pipefail

# Continuous verbose output
set -x

echo "=== DEDUPE COMMUNE: MOVE NON-CANONICAL FLAC FILES TO /Volumes/COMMUNE/90_REJECTED ==="

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO/scripts/shell/_resolve_db_path.sh"

FINAL_DB="${FINAL_DB:-}"
CANON_DB="${CANON_DB:-}"
SRC_ROOT="${SRC_ROOT:-}"
DEST_ROOT="${DEST_ROOT:-}"
LOG_DIR="${LOG_DIR:-$REPO/artifacts/logs}"

FINAL_DB="$(require_db_value "$FINAL_DB" "FINAL_DB")"
CANON_DB="$(require_db_value "$CANON_DB" "CANON_DB")"
SRC_ROOT="$(require_db_value "$SRC_ROOT" "SRC_ROOT")"
DEST_ROOT="$(require_db_value "$DEST_ROOT" "DEST_ROOT")"

FINAL_DB="$(resolve_db_path "read" "$FINAL_DB")"
CANON_DB="$(resolve_db_path "read" "$CANON_DB")"
mkdir -p "$LOG_DIR"

MOVE_LIST="$LOG_DIR/commune_dupe_paths_flac.txt"
MOVE_LOG="$LOG_DIR/commune_dupe_moves.log"

echo

echo "FINAL DB : $FINAL_DB"
echo "CANON DB : $CANON_DB"
echo "DEST ROOT: $DEST_ROOT"
echo "LIST     : $MOVE_LIST"
echo "LOG      : $MOVE_LOG"

if [[ ! -d "$(dirname "$DEST_ROOT")" ]]; then
  echo "ERROR: destination parent volume does not exist: $(dirname "$DEST_ROOT")" >&2
  exit 1
fi

mkdir -p "$DEST_ROOT"

echo
echo "=== STEP 1: BUILD LIST OF NON-CANONICAL FLAC PATHS ON ${SRC_ROOT} ==="

# Regenerate list every run
rm -f "$MOVE_LIST"

sqlite3 "$FINAL_DB" <<SQL
ATTACH '$CANON_DB' AS canon;

.mode tabs
.headers off
.output '$MOVE_LIST'

-- All paths that are present in FINAL but NOT present in CANON,
-- restricted to /Volumes/COMMUNE/20_ACCEPTED and *.flac
SELECT f.path
FROM library_files AS f
LEFT JOIN canon.library_files AS c
  ON f.path = c.path
WHERE c.path IS NULL
  AND f.path LIKE '${SRC_ROOT}/%'
  AND f.path LIKE '%.flac';

.output stdout

DETACH canon;
SQL

if [[ ! -s "$MOVE_LIST" ]]; then
  echo "No non-canonical FLAC files found to move. Nothing to do."
  exit 0
fi

TOTAL=$(wc -l < "$MOVE_LIST" | tr -d ' ')
echo "Paths to move: $TOTAL"
echo "List saved to: $MOVE_LIST"

echo
echo "=== STEP 2: MOVE FILES OFF /Volumes/COMMUNE/20_ACCEPTED (PRESERVE STRUCTURE) ==="
echo "Moves will be logged to: $MOVE_LOG"
echo

moved=0
skipped_missing=0
skipped_error=0

# Append to log, but mark start of run
{
  echo "===================================================================="
  echo "Run at: $(date)"
  echo "Source DB: $FINAL_DB"
  echo "Canon DB : $CANON_DB"
  echo "Destination root: $DEST_ROOT"
} >> "$MOVE_LOG"

while IFS= read -r src; do
  # Skip empty lines
  [[ -z "$src" ]] && continue

  # Only act on files that still exist (resumable behaviour)
  if [[ ! -f "$src" ]]; then
    echo "SKIP (missing): $src"
    echo "[SKIP missing] $src" >> "$MOVE_LOG"
    ((skipped_missing++))
    continue
  fi

  # Compute relative path under SRC_ROOT
  rel="${src#${SRC_ROOT}/}"
  dest="$DEST_ROOT/$rel"

  dest_dir=$(dirname "$dest")
  if [[ ! -d "$dest_dir" ]]; then
    echo "MKDIR: $dest_dir"
    mkdir -pv "$dest_dir" || {
      echo "ERROR: cannot create directory: $dest_dir" >&2
      echo "[ERROR mkdir] $src -> $dest_dir" >> "$MOVE_LOG"
      ((skipped_error++))
      continue
    }
  fi

  echo "MOVE: $src"
  echo "      -> $dest"

  if mv -v "$src" "$dest" | tee -a "$MOVE_LOG"; then
    ((moved++))
  else
    echo "ERROR: mv failed for: $src" >&2
    echo "[ERROR mv] $src -> $dest" >> "$MOVE_LOG"
    ((skipped_error++))
  fi

done < "$MOVE_LIST"

echo
echo "=== SUMMARY ==="
echo "Total listed : $TOTAL"
echo "Moved        : $moved"
echo "Missing (skip): $skipped_missing"
echo "Errors (skip): $skipped_error"
echo
echo "Details logged to: $MOVE_LOG"
echo "Duplicate FLAC files have been moved under: $DEST_ROOT"
echo "You can re-run this script safely: it will skip already-moved files."
