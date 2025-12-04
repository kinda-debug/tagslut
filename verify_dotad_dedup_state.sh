#!/usr/bin/env bash
set -euo pipefail

REPO="${HOME}/dedupe_repo_reclone"
FINAL_DB="${REPO}/artifacts/db/library_final.db"
CANON_DB="${REPO}/artifacts/db/library_canonical_full.db"
SRC_ROOT="/Volumes/dotad"
DEST_ROOT="/Volumes/bad/DOTAD_DEDUPED"
LOG_DIR="${REPO}/artifacts/logs"

mkdir -p "${LOG_DIR}"

NONCANON_LIST="${LOG_DIR}/dotad_noncanonical_flac_paths.txt"
NONCANON_PRESENT="${LOG_DIR}/dotad_noncanonical_still_on_dotad.txt"
NONCANON_MOVED_OK="${LOG_DIR}/dotad_noncanonical_moved_ok.txt"
NONCANON_MOVED_MISSING="${LOG_DIR}/dotad_noncanonical_missing_on_bad.txt"

CANON_LIST="${LOG_DIR}/canonical_flac_paths.txt"
CANON_MISSING="${LOG_DIR}/canonical_missing_on_disk.txt"

echo "=== VERIFY DEDUP STATE: /Volumes/dotad vs canonical DBs ==="
echo "FINAL DB : ${FINAL_DB}"
echo "CANON DB : ${CANON_DB}"
echo "SRC ROOT : ${SRC_ROOT}"
echo "DEST ROOT: ${DEST_ROOT}"
echo "LOG DIR  : ${LOG_DIR}"
echo

if [[ ! -f "${FINAL_DB}" ]]; then
  echo "ERROR: FINAL_DB not found: ${FINAL_DB}"
  exit 1
fi

if [[ ! -f "${CANON_DB}" ]]; then
  echo "ERROR: CANON_DB not found: ${CANON_DB}"
  exit 1
fi

echo "=== 1) DB-LEVEL COUNTS ==="
total_flac_dotad=$(sqlite3 "${FINAL_DB}" "
  SELECT COUNT(*)
  FROM library_files
  WHERE path LIKE '${SRC_ROOT}/%' AND lower(path) LIKE '%.flac';
")
echo "Total FLAC entries on dotad in FINAL_DB: ${total_flac_dotad}"

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
echo "Non-canonical FLAC entries on dotad (DB): ${noncanon_count_db}"
echo "Non-canonical list: ${NONCANON_LIST}"
echo

echo "=== 2) CHECK NON-CANONICAL FILES ON DISK ==="
> "${NONCANON_PRESENT}"
> "${NONCANON_MOVED_OK}"
> "${NONCANON_MOVED_MISSING}"

still_on_dotad=0
moved_ok=0
moved_missing=0

while IFS= read -r src; do
  [[ -z "${src}" ]] && continue

  # Where it should have been moved to (preserving structure)
  # /Volumes/dotad/...  -> /Volumes/bad/DOTAD_DEDUPED/...
  dest="${DEST_ROOT}${src#${SRC_ROOT}}"

  if [[ -f "${src}" ]]; then
    ((still_on_dotad++))
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

echo "Non-canonical FLACs still present on dotad: ${still_on_dotad}"
echo "Non-canonical FLACs found on /Volumes/bad/DOTAD_DEDUPED: ${moved_ok}"
echo "Non-canonical FLACs missing on /Volumes/bad/DOTAD_DEDUPED (dest): ${moved_missing}"
echo "  Still on dotad list : ${NONCANON_PRESENT}"
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
echo "  Total FLAC on dotad (DB):          ${total_flac_dotad}"
echo "  Non-canonical FLAC on dotad (DB):  ${noncanon_count_db}"
echo "  Non-canonical still on dotad:      ${still_on_dotad}"
echo "  Non-canonical found on /bad:       ${moved_ok}"
echo "  Non-canonical missing on /bad:     ${moved_missing}"
echo "  Canonical FLAC total:              ${canon_total}"
echo "  Canonical missing on disk:         ${canon_missing}"
