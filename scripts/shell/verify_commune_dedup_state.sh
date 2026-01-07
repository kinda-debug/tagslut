#!/usr/bin/env bash
set -euo pipefail

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

mkdir -p "${LOG_DIR}"

NONCANON_LIST="${LOG_DIR}/commune_noncanonical_flac_paths.txt"
NONCANON_PRESENT="${LOG_DIR}/commune_noncanonical_still_on_accepted.txt"
NONCANON_MOVED_OK="${LOG_DIR}/commune_noncanonical_moved_ok.txt"
NONCANON_MOVED_MISSING="${LOG_DIR}/commune_noncanonical_missing_on_rejected.txt"

CANON_LIST="${LOG_DIR}/canonical_flac_paths.txt"
CANON_MISSING="${LOG_DIR}/canonical_missing_on_disk.txt"

echo "=== VERIFY DEDUP STATE: /Volumes/COMMUNE/20_ACCEPTED vs canonical DBs ==="
echo "FINAL DB : ${FINAL_DB}"
echo "CANON DB : ${CANON_DB}"
echo "SRC ROOT : ${SRC_ROOT}"
echo "DEST ROOT: ${DEST_ROOT}"
echo "LOG DIR  : ${LOG_DIR}"
echo

echo "=== 1) DB-LEVEL COUNTS ==="
total_flac_accepted=$(sqlite3 "${FINAL_DB}" "
  SELECT COUNT(*)
  FROM library_files
  WHERE path LIKE '${SRC_ROOT}/%' AND lower(path) LIKE '%.flac';
")
echo "Total FLAC entries on accepted in FINAL_DB: ${total_flac_accepted}"

sqlite3 "${FINAL_DB}" <<SQL > "${NONCANON_LIST}"
ATTACH '${CANON_DB}' AS canon;
SELECT f.path
FROM library_files f
LEFT JOIN canon.library_files c ON f.path = c.path
WHERE f.path LIKE '${SRC_ROOT}/%'
  AND lower(f.path) LIKE '%.flac'
  AND c.path IS NULL
ORDER BY f.path;
DETACH canon;
SQL

noncanon_count_db=$(wc -l < "${NONCANON_LIST}" | tr -d ' ')
echo "Non-canonical FLAC entries on accepted (DB): ${noncanon_count_db}"
echo "Non-canonical list: ${NONCANON_LIST}"
echo

echo "=== 2) CHECK NON-CANONICAL FILES ON DISK ==="
> "${NONCANON_PRESENT}"
> "${NONCANON_MOVED_OK}"
> "${NONCANON_MOVED_MISSING}"

still_on_accepted=0
moved_ok=0
moved_missing=0

while IFS= read -r src; do
  [[ -z "${src}" ]] && continue

  # Where it should have been moved to (preserving structure)
  # /Volumes/COMMUNE/20_ACCEPTED/...  -> /Volumes/COMMUNE/90_REJECTED/...
  dest="${DEST_ROOT}${src#${SRC_ROOT}}"

  if [[ -f "${src}" ]]; then
    ((still_on_accepted++))
    echo "${src}" >> "${NONCANON_PRESENT}"
  fi

  if [[ -f "${dest}" ]]; then
    ((moved_ok++))
    echo "${dest}" >> "${NONCANON_MOVED_OK}"
  else
    ((moved_missing++))
    echo "${dest}" >> "${NONCANON_MOVED_MISSING}"
  fi
done < "${NONCANON_LIST}"

echo "Non-canonical FLACs still present on accepted: ${still_on_accepted}"
echo "Non-canonical FLACs found on /Volumes/COMMUNE/90_REJECTED: ${moved_ok}"
echo "Non-canonical FLACs missing on /Volumes/COMMUNE/90_REJECTED (dest): ${moved_missing}"
echo "  Still on accepted list : ${NONCANON_PRESENT}"
echo "  Dest missing list   : ${NONCANON_MOVED_MISSING}"
echo

echo "=== 3) CHECK CANONICAL FLAC FILES EXIST ON DISK ==="

sqlite3 "${CANON_DB}" "
  SELECT path
  FROM library_files
  WHERE lower(path) LIKE '%.flac'
  ORDER BY path;
" > "${CANON_LIST}"

> "${CANON_MISSING}"

canon_total=$(wc -l < "${CANON_LIST}" | tr -d ' ')
canon_missing=0
canon_ok=0

while IFS= read -r p; do
  [[ -z "${p}" ]] && continue
  if [[ -f "${p}" ]]; then
    ((canon_ok++))
  else
    ((canon_missing++))
    echo "${p}" >> "${CANON_MISSING}"
  fi
done < "${CANON_LIST}"

echo "Canonical FLAC entries in CANON_DB: ${canon_total}"
echo "Canonical FLAC files found on disk : ${canon_ok}"
echo "Canonical FLAC files missing       : ${canon_missing}"
echo "Canonical missing list: ${CANON_MISSING}"
echo

echo "=== DONE: Verification summary ==="
echo "  Total FLAC on accepted (DB):          ${total_flac_accepted}"
echo "  Non-canonical FLAC on accepted (DB):  ${noncanon_count_db}"
echo "  Non-canonical still on accepted:      ${still_on_accepted}"
echo "  Non-canonical found on rejected:      ${moved_ok}"
echo "  Non-canonical missing on rejected:    ${moved_missing}"
echo "  Canonical FLAC total:              ${canon_total}"
echo "  Canonical missing on disk:         ${canon_missing}"
