#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# CONFIGURATION
###############################################################################

REPO="$HOME/dedupe_repo_reclone"
VENV="$REPO/.venv/bin/activate"

SCAN_DIR="$REPO/artifacts/db/rescan_all"
FINAL_DB="$REPO/artifacts/db/library_final.db"
TMP_DB="${FINAL_DB}.tmp"

# Export volume with enough free space
EXPORT_VOLUME="/Volumes/bad"

TS="$(date +%Y%m%d_%H%M%S)"
EXPORT_ROOT="$EXPORT_VOLUME/LIBRARY_EXPORT_${TS}"
EXPORT_DB_REPO="$REPO/artifacts/db/library_export_final.sqlite"
EXPORT_DB_EXPORT="$EXPORT_ROOT/library_export_final.sqlite"

# All roots to be scanned under /Volumes/dotad
ROOTS=(
  "/Volumes/dotad/_QUARANTINE_DUPES"
  "/Volumes/dotad/DEDUPER_QUARANTINE_20251201_122233"
  "/Volumes/dotad/DEDUPER_QUARANTINE_20251201_122648"
  "/Volumes/dotad/DEDUPER_RESCAN"
  "/Volumes/dotad/G_DUPEGURU"
  "/Volumes/dotad/MUSIC"
  "/Volumes/dotad/NEW_LIBRARY"
  "/Volumes/dotad/NEW_LIBRARY_CLEAN"
  "/Volumes/dotad/NEW_MUSIC"
  "/Volumes/dotad/QUARANTINE_AUTO_GLOBAL"
  "/Volumes/dotad/RECOVERED_FROM_MISSING"
)

###############################################################################
# SANITY CHECKS
###############################################################################

echo "=== ACTIVATING VIRTUALENV ==="
if [[ -f "$VENV" ]]; then
  # shellcheck source=/dev/null
  source "$VENV"
else
  echo "ERROR: Virtualenv not found at $VENV" >&2
  exit 1
fi

echo "Using python: $(command -v python)"
echo

if [[ ! -d "$EXPORT_VOLUME" ]]; then
  echo "ERROR: Export volume $EXPORT_VOLUME not found." >&2
  exit 1
fi

mkdir -p "$SCAN_DIR"
mkdir -p "$REPO/artifacts/db"

###############################################################################
# STEP 1: SCAN ALL ROOTS INTO PER-ROOT DBS (RESUMABLE)
###############################################################################

echo "=== SCANNING ALL ROOTS INTO PER-ROOT DBs ==="

for root in "${ROOTS[@]}"; do
  if [[ ! -d "$root" ]]; then
    echo "  [SKIP] $root (not found)"
    continue
  fi

  root_basename="$(basename "$root")"
  out_db="$SCAN_DIR/${root_basename}.sqlite"

  if [[ -f "$out_db" ]]; then
    echo "  [REUSE] $root -> $out_db (already exists)"
    continue
  fi

  echo "  [SCAN]  $root -> $out_db"
  python -m dedupe.cli scan-library \
    --root "$root" \
    --out "$out_db" \
    --progress
  done

echo
echo "=== LISTING SCAN DBS ==="
ls -l "$SCAN_DIR"
echo

###############################################################################
# STEP 2: BUILD MERGED FULL-SCHEMA library_final.db
###############################################################################

echo "=== BUILDING MERGED FINAL DB ==="

first_db=""
for db in "$SCAN_DIR"/*.sqlite; do
  first_db="$db"
  break
done

if [[ -z "${first_db:-}" ]]; then
  echo "ERROR: No scan DBs found in $SCAN_DIR" >&2
  exit 1
fi

echo "Using schema from: $first_db"
rm -f "$TMP_DB"

# Initialize target DB with schema and data from first DB
sqlite3 "$TMP_DB" <<SQL
ATTACH '$first_db' AS src;
CREATE TABLE library_files AS
SELECT * FROM src.library_files;
DETACH src;
SQL

# Merge remaining DBs
for db in "$SCAN_DIR"/*.sqlite; do
  if [[ "$db" == "$first_db" ]]; then
    continue
  fi
  echo "  Merging $db"
  sqlite3 "$TMP_DB" <<SQL
ATTACH '$db' AS scan;
INSERT OR REPLACE INTO library_files
SELECT * FROM scan.library_files;
DETACH scan;
SQL
done

echo
echo "=== BASIC STATS ON MERGED DB ==="
echo "Total rows:"
sqlite3 "$TMP_DB" "SELECT COUNT(*) FROM library_files;"

echo
echo "Distinct root prefixes (first component under /Volumes/dotad):"
sqlite3 "$TMP_DB" '
SELECT DISTINCT
  substr(
    path,
    1,
    instr(substr(path, 16), "/") + 15
  ) AS root
FROM library_files
WHERE path LIKE "/Volumes/dotad/%"
ORDER BY root;
'

echo
echo "Rows with missing checksum (should be rare, mostly non-audio or failed reads):"
sqlite3 "$TMP_DB" '
SELECT COUNT(*)
FROM library_files
WHERE checksum IS NULL OR checksum = "";
'

echo
echo "Rows with missing extra_json:"
sqlite3 "$TMP_DB" '
SELECT COUNT(*)
FROM library_files
WHERE extra_json IS NULL OR extra_json = "";
'

echo
echo "Top 20 checksums with >1 occurrence (raw dup clusters):"
sqlite3 "$TMP_DB" '
SELECT checksum, COUNT(*) c
FROM library_files
WHERE checksum IS NOT NULL AND checksum <> ""
GROUP BY checksum
HAVING c > 1
ORDER BY c DESC
LIMIT 20;
'

echo
echo "=== BUILDING CANONICAL TABLE ==="

sqlite3 "$TMP_DB" <<'SQL'
DROP TABLE IF EXISTS canonical;

CREATE TABLE canonical AS
SELECT *
FROM library_files
WHERE checksum IS NOT NULL
  AND checksum <> ''
  AND checksum <> 'd41d8cd98f00b204e9800998ecf8427e'
  AND (checksum, duration, bit_rate, size_bytes) IN (
    SELECT
      checksum,
      MAX(duration) AS max_duration,
      MAX(bit_rate) AS max_bit_rate,
      MAX(size_bytes) AS max_size
    FROM library_files
    WHERE checksum IS NOT NULL
      AND checksum <> ''
      AND checksum <> 'd41d8cd98f00b204e9800998ecf8427e'
    GROUP BY checksum
  );
SQL

canonical_count="$(sqlite3 "$TMP_DB" 'SELECT COUNT(*) FROM canonical;')"
total_count="$(sqlite3 "$TMP_DB" 'SELECT COUNT(*) FROM library_files;')"

echo "Total rows in library_files: $total_count"
echo "Canonical rows (unique checksums, best quality): $canonical_count"
echo

echo "=== FINALIZING MERGED DB ==="
mv "$TMP_DB" "$FINAL_DB"
echo "Final merged DB with canonical table: $FINAL_DB"
echo

###############################################################################
# STEP 3: EXPORT CANONICAL FILES TO EXPORT_ROOT (RESUMABLE, NON-DESTRUCTIVE)
###############################################################################

echo "=== CANONICAL EXPORT + RESCAN PIPELINE ==="
echo "Using library DB:           $FINAL_DB"
echo "Export root (snapshot):     $EXPORT_ROOT"
echo "Export DB (in repo):        $EXPORT_DB_REPO"
echo "Export DB (next to files):  $EXPORT_DB_EXPORT"
echo

mkdir -p "$EXPORT_ROOT"

echo "=== EXPORTING CANONICAL FILES TO $EXPORT_ROOT ==="

canonical_paths_file="$(mktemp)"
sqlite3 "$FINAL_DB" 'SELECT path FROM canonical;' > "$canonical_paths_file"

total_canonical="$(wc -l < "$canonical_paths_file" | tr -d ' ')"
echo "Total canonical paths to process: $total_canonical"

idx=0
while IFS= read -r src; do
  idx=$((idx + 1))

  if [[ -z "$src" ]]; then
    continue
  fi

  if [[ ! -f "$src" ]]; then
    echo "SKIP [$idx/$total_canonical] (missing on disk): $src"
    continue
  fi

  # Strip the /Volumes/dotad prefix to build relative path under EXPORT_ROOT
  rel="${src#/Volumes/dotad}"
  # If the path does not start with /Volumes/dotad, fall back to using full path under EXPORT_ROOT
  if [[ "$rel" == "$src" ]]; then
    # Not under /Volumes/dotad; keep as-is but rooted under export
    rel="$src"
  fi

  dst="$EXPORT_ROOT/$rel"
  dst_dir="$(dirname "$dst")"

  if [[ -f "$dst" ]]; then
    echo "SKIP [$idx/$total_canonical] (already exists): $dst"
    continue
  fi

  echo "COPY [$idx/$total_canonical]"
  echo "  from: $src"
  echo "  to:   $dst"

  mkdir -p "$dst_dir"
  cp -p "$src" "$dst" || {
    echo "ERROR copying $src -> $dst" >&2
  }
done < "$canonical_paths_file"

rm -f "$canonical_paths_file"

echo
echo "=== EXPORT SUMMARY ==="
echo "Export root contents (file count):"
find "$EXPORT_ROOT" -type f | wc -l
echo

###############################################################################
# STEP 4: RESCAN EXPORT ROOT INTO CLEAN DB
###############################################################################

echo "=== RESCANNING EXPORT ROOT INTO CLEAN DB ==="
echo "Target DB (repo): $EXPORT_DB_REPO"
echo

rm -f "$EXPORT_DB_REPO"

python -m dedupe.cli scan-library \
  --root "$EXPORT_ROOT" \
  --out "$EXPORT_DB_REPO" \
  --progress

echo
echo "=== BASIC STATS ON EXPORT DB ==="
sqlite3 "$EXPORT_DB_REPO" "SELECT COUNT(*) FROM library_files;"

echo
echo "=== COPYING EXPORT DB NEXT TO FILES ==="
cp -f "$EXPORT_DB_REPO" "$EXPORT_DB_EXPORT"

echo
echo "=== DONE ==="
echo "Canonical export directory:      $EXPORT_ROOT"
echo "Export DB in repo:               $EXPORT_DB_REPO"
echo "Export DB next to files:         $EXPORT_DB_EXPORT"
echo "Source library DB was not modified or deleted."
