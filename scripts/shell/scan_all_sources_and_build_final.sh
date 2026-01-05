#!/usr/bin/env bash
set -euo pipefail
set -x

############################################
# CONFIG
############################################

REPO="$HOME/dedupe_repo_reclone"
VENV="$REPO/.venv/bin/activate"

# Use venv Python for all scans
VENV_PY="$REPO/.venv/bin/python3"

# Where per-root scan DBs will live
SCAN_DIR="$REPO/artifacts/db/rescan_all"

# Final merged DB
FINAL_DB="$REPO/artifacts/db/library_final.db"
TMP_DB="$FINAL_DB.tmp"

# All roots you want scanned
ROOTS=(
  "/Volumes/COMMUNE/10_STAGING"
  "/Volumes/COMMUNE/20_ACCEPTED"
)

############################################
# ENV
############################################

echo "=== ACTIVATING VIRTUALENV ==="
# If you sometimes use system Python, adjust this line
# or comment it out. For now, we assume .venv is correct.
if [[ -f "$VENV" ]]; then
  # shellcheck disable=SC1090
  source "$VENV"
else
  echo "WARNING: venv not found at $VENV, continuing with system python" >&2
fi

mkdir -p "$SCAN_DIR"
mkdir -p "$REPO/artifacts/db"

############################################
# 1. SCAN ALL ROOTS (RESUMABLE)
############################################

echo
echo "=== SCANNING ALL ROOTS INTO PER-ROOT DBs ==="

for root in "${ROOTS[@]}"; do
  if [[ ! -d "$root" ]]; then
    echo "WARNING: root does not exist, skipping: $root" >&2
    continue
  fi

  # Turn "/Volumes/COMMUNE/10_STAGING" into "10_STAGING.sqlite" etc.
  root_basename=$(basename "$root")
  out_db="$SCAN_DIR/${root_basename}.sqlite"

  if [[ -f "$out_db" ]]; then
    echo "  [SKIP] Existing scan DB found, reusing: $out_db"
    echo "         Delete it manually if you want a fresh rescan for $root"
    continue
  fi

  echo "  [SCAN] $root -> $out_db"
  zone_arg=""
  if [[ "$root" == *"/10_STAGING" ]]; then
    zone_arg="--zone staging"
  elif [[ "$root" == *"/20_ACCEPTED" ]]; then
    zone_arg="--zone accepted"
  fi

  "$VENV_PY" -m dedupe.cli scan-library \
    --root "$root" \
    --out "$out_db" \
    --progress \
    $zone_arg
  
done

echo
echo "=== LISTING SCAN DBS ==="
ls -l "$SCAN_DIR"

############################################
# 2. BUILD MERGED library_final.db WITH FULL SCHEMA
############################################

echo
echo "=== BUILDING MERGED FINAL DB ==="

# Find first scan DB to clone schema from
first_db=""
for db in "$SCAN_DIR"/*.sqlite; do
  first_db="$db"
  break
done

if [[ -z "${first_db:-}" ]]; then
  echo "ERROR: No scan DBs found in $SCAN_DIR. Nothing to merge." >&2
  exit 1
fi

echo "Using schema from: $first_db"

# Reset tmp DB
rm -f "$TMP_DB"

# Clone full schema of library_files from first scan DB
sqlite3 "$TMP_DB" <<SQL
ATTACH '$first_db' AS scan;
CREATE TABLE library_files AS
  SELECT *
  FROM scan.library_files
  WHERE 0;  -- create table with same columns, but no rows
DETACH scan;
SQL

echo
echo "=== MERGING ALL SCAN DBS INTO FINAL DB (FULL SCHEMA) ==="

for db in "$SCAN_DIR"/*.sqlite; do
  echo "  Merging $db"
  sqlite3 "$TMP_DB" <<SQL
ATTACH '$db' AS scan;
INSERT OR REPLACE INTO library_files
SELECT *
FROM scan.library_files;
DETACH scan;
SQL
done

echo
echo "=== BASIC STATS ON MERGED DB ==="

echo "Total rows:"
sqlite3 "$TMP_DB" "SELECT COUNT(*) FROM library_files;"

echo
echo "Distinct root prefixes (first component under /Volumes/COMMUNE):"
sqlite3 "$TMP_DB" "
SELECT DISTINCT
  substr(
    path,
    1,
    instr(substr(path, 16), '/') + 15
  ) AS root
FROM library_files
ORDER BY root;
"

echo
echo "Rows with missing checksum (should be rare, mostly non-audio or failed reads):"
sqlite3 "$TMP_DB" "
SELECT COUNT(*) 
FROM library_files
WHERE checksum IS NULL OR checksum='';
"

echo
echo "Rows with missing extra_json:"
sqlite3 "$TMP_DB" "
SELECT COUNT(*) 
FROM library_files
WHERE extra_json IS NULL OR extra_json='';
"

echo
echo "Top 20 checksums with >1 occurrence (raw dup clusters):"
sqlite3 "$TMP_DB" "
SELECT checksum, COUNT(*) c
FROM library_files
WHERE checksum IS NOT NULL AND checksum <> ''
GROUP BY checksum
HAVING c > 1
ORDER BY c DESC
LIMIT 20;
"

echo
echo "=== FINALIZING MERGED DB ==="
mv "$TMP_DB" "$FINAL_DB"

echo "Final merged DB: $FINAL_DB"

############################################
# DONE
############################################

echo
echo "=== ALL DONE ==="
echo "All requested roots under /Volumes/COMMUNE have been scanned (or reused from existing scan DBs)."
echo "Merged, full-schema library is now in: $FINAL_DB"
echo "You can now:"
echo "  - Run your existing canonical/dedupe pipeline on library_final.db"
echo "  - Or run the export+rescan script against this DB for a clean export."
