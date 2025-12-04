#!/usr/bin/env bash
set -euo pipefail

# Canonical-only export + rescan pipeline
# - Uses existing full-schema library_final.db
# - Builds a fresh canonical table
# - Exports only canonical files into /Volumes/dotad/LIBRARY_EXPORT_<timestamp>/
# - Rescans that export into a clean SQLite DB
# - No deletions or moves on /Volumes/dotad

REPO="$HOME/dedupe_repo_reclone"
VENV="$REPO/.venv/bin/activate"
DB="$REPO/artifacts/db/library_final.db"

# Guard: Ensure venv Python exists
if [[ ! -x "$REPO/.venv/bin/python3" ]]; then
  echo "ERROR: venv Python missing. Recreate with: python3 -m venv .venv"
  exit 1
fi

# ----- basic checks -----

if [[ ! -d "/Volumes/dotad" ]]; then
  echo "ERROR: /Volumes/dotad is not mounted."
  exit 1
fi

if [[ ! -f "$DB" ]]; then
  echo "ERROR: Library DB not found: $DB"
  exit 1
fi

if [[ -f "$VENV" ]]; then
  echo "=== ACTIVATING VIRTUALENV ==="
  # shellcheck disable=SC1090
  source "$VENV"
else
  echo "WARNING: Virtualenv not found at $VENV; continuing with system Python."
fi

# ----- derive export root -----

TS=$(date +%Y%m%d_%H%M%S)
EXPORT_ROOT="/Volumes/bad/LIBRARY_EXPORT_${TS}"
EXPORT_DB_REPO="$REPO/artifacts/db/library_export_final.sqlite"
EXPORT_DB_IN_PLACE="$EXPORT_ROOT/library_export_final.sqlite"

echo
echo "=== CANONICAL EXPORT + RESCAN PIPELINE ==="
echo "Using library DB:         $DB"
echo "Export root (snapshot):   $EXPORT_ROOT"
echo "Export DB (in repo):      $EXPORT_DB_REPO"
echo "Export DB (next to files): $EXPORT_DB_IN_PLACE"
echo

mkdir -p "$EXPORT_ROOT"
mkdir -p "$(dirname "$EXPORT_DB_REPO")"

# ----- build canonical table -----

echo "=== REBUILDING CANONICAL TABLE IN library_final.db ==="

sqlite3 "$DB" <<'SQL'
DROP TABLE IF EXISTS canonical;

CREATE TABLE canonical AS
SELECT *
FROM library_files
WHERE checksum IS NOT NULL
  AND checksum <> ''
  AND (checksum, duration, bit_rate, size_bytes) IN (
      SELECT
          checksum,
          MAX(duration)   AS max_duration,
          MAX(bit_rate)   AS max_bit_rate,
          MAX(size_bytes) AS max_size_bytes
      FROM library_files
      WHERE checksum IS NOT NULL
        AND checksum <> ''
      GROUP BY checksum
  );

CREATE INDEX IF NOT EXISTS idx_canonical_checksum_path
ON canonical(checksum, path);
SQL

canonical_count=$(sqlite3 "$DB" "SELECT COUNT(*) FROM canonical;")
echo "Canonical rows: $canonical_count"

if [[ "$canonical_count" -eq 0 ]]; then
  echo "ERROR: canonical table is empty. Aborting export."
  exit 1
fi

# ----- export canonical files -----

echo
echo "=== EXPORTING CANONICAL FILES TO $EXPORT_ROOT ==="

total_canonical="$canonical_count"
echo "Total canonical paths to process: $total_canonical"

copied=0
skipped=0
missing=0
processed=0

# Use process substitution to keep counters in this shell
while IFS= read -r src; do
  processed=$((processed + 1))

  # Expect all paths to be under /Volumes/dotad/...
  if [[ -z "$src" ]]; then
    continue
  fi

  if [[ ! -f "$src" ]]; then
    echo "MISSING [$processed/$total_canonical]: $src"
    missing=$((missing + 1))
    continue
  fi

  # Strip the /Volumes/dotad/ prefix to build relative path under EXPORT_ROOT
  # If the path does not start with that prefix, fallback to flat copy with basename.
  if [[ "$src" == /Volumes/dotad/* ]]; then
    rel="${src#/Volumes/dotad/}"
    dest="$EXPORT_ROOT/$rel"
  else
    # unexpected root: keep it but do not try to mirror unknown tree
    basef=$(basename "$src")
    dest="$EXPORT_ROOT/$basef"
  fi

  dest_dir=$(dirname "$dest")
  mkdir -p "$dest_dir"

  if [[ -f "$dest" ]]; then
    # resumable: do not overwrite
    echo "SKIP (exists) [$processed/$total_canonical]: $dest"
    skipped=$((skipped + 1))
    continue
  fi

  echo "COPY [$processed/$total_canonical]"
  echo "  from: $src"
  echo "  to:   $dest"
  cp -p "$src" "$dest"
  copied=$((copied + 1))

done < <(sqlite3 -noheader "$DB" "SELECT path FROM canonical;")

echo
echo "=== EXPORT SUMMARY ==="
echo "Canonical rows:      $total_canonical"
echo "Copied (new files):  $copied"
echo "Skipped (already in export): $skipped"
echo "Missing on disk:     $missing"
echo "Export root:         $EXPORT_ROOT"

# If nothing was copied and nothing exists, warn.
existing_in_export=$(find "$EXPORT_ROOT" -type f 2>/dev/null | wc -l | tr -d ' ')
if [[ "$existing_in_export" -eq 0 ]]; then
  echo "WARNING: Export directory contains no files. Check paths in canonical table."
fi

# ----- rescan export root into a clean DB -----

echo
echo "=== RESCANNING EXPORT ROOT INTO CLEAN DB ==="
echo "Target DB (repo): $EXPORT_DB_REPO"

rm -f "$EXPORT_DB_REPO"

"$REPO/.venv/bin/python3" -m dedupe.cli scan-library \
  --root "$EXPORT_ROOT" \
  --out "$EXPORT_DB_REPO" \
  --progress

echo
echo "=== BASIC STATS ON EXPORT DB ==="
sqlite3 "$EXPORT_DB_REPO" "SELECT COUNT(*) AS exported_rows FROM library_files;"

# Also place a copy next to the files for portability
echo
echo "=== COPYING EXPORT DB NEXT TO FILES ==="
cp -p "$EXPORT_DB_REPO" "$EXPORT_DB_IN_PLACE"

echo
echo "=== DONE ==="
echo "Canonical export directory:      $EXPORT_ROOT"
echo "Export DB in repo:              $EXPORT_DB_REPO"
echo "Export DB next to files:        $EXPORT_DB_IN_PLACE"
echo "Source library DB was not modified or deleted."
