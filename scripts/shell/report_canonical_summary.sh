#!/usr/bin/env bash
set -euo pipefail

REPO="${HOME}/dedupe_repo_reclone"
CANON_DB="${REPO}/artifacts/db/library_canonical_full.db"
LOG_DIR="${REPO}/artifacts/logs"

mkdir -p "${LOG_DIR}"

ts="$(date +'%Y%m%d_%H%M%S')"
SUMMARY_LOG="${LOG_DIR}/canonical_summary_${ts}.log"

echo "=== CANONICAL LIBRARY SUMMARY ==="
echo "CANON DB : ${CANON_DB}"
echo "LOG FILE : ${SUMMARY_LOG}"
echo

if [[ ! -f "${CANON_DB}" ]]; then
  echo "ERROR: CANON_DB not found: ${CANON_DB}"
  exit 1
fi

{
  echo "=== CANONICAL LIBRARY SUMMARY ==="
  echo "Timestamp: ${ts}"
  echo "Canonical DB: ${CANON_DB}"
  echo

  echo "1) Global counts (FLAC only):"
  total_flac=$(sqlite3 "${CANON_DB}" "
    SELECT COUNT(*)
    FROM library_files
    WHERE lower(path) LIKE '%.flac';
  ")
  accepted_flac=$(sqlite3 "${CANON_DB}" "
    SELECT COUNT(*)
    FROM library_files
    WHERE path LIKE '/Volumes/COMMUNE/20_ACCEPTED/%' AND lower(path) LIKE '%.flac';
  ")
  staging_flac=$(sqlite3 "${CANON_DB}" "
    SELECT COUNT(*)
    FROM library_files
    WHERE path LIKE '/Volumes/COMMUNE/10_STAGING/%' AND lower(path) LIKE '%.flac';
  ")
  rejected_flac=$(sqlite3 "${CANON_DB}" "
    SELECT COUNT(*)
    FROM library_files
    WHERE path LIKE '/Volumes/COMMUNE/90_REJECTED/%' AND lower(path) LIKE '%.flac';
  ")
  other_flac=$(sqlite3 "${CANON_DB}" "
    SELECT COUNT(*)
    FROM library_files
    WHERE path NOT LIKE '/Volumes/COMMUNE/20_ACCEPTED/%'
      AND path NOT LIKE '/Volumes/COMMUNE/10_STAGING/%'
      AND path NOT LIKE '/Volumes/COMMUNE/90_REJECTED/%'
      AND lower(path) LIKE '%.flac';
  ")

  echo "  Total canonical FLAC tracks : ${total_flac}"
  echo "  On /Volumes/COMMUNE/20_ACCEPTED : ${accepted_flac}"
  echo "  On /Volumes/COMMUNE/10_STAGING  : ${staging_flac}"
  echo "  On /Volumes/COMMUNE/90_REJECTED : ${rejected_flac}"
  echo "  On other volumes            : ${other_flac}"
  echo

  echo "2) COMMUNE canonical FLACs by zone:"
  sqlite3 "${CANON_DB}" "
    SELECT bucket, COUNT(*) AS count
    FROM (
      SELECT
        CASE
          WHEN path LIKE '/Volumes/COMMUNE/20_ACCEPTED/%' THEN 'ACCEPTED'
          WHEN path LIKE '/Volumes/COMMUNE/10_STAGING/%' THEN 'STAGING'
          WHEN path LIKE '/Volumes/COMMUNE/90_REJECTED/%' THEN 'REJECTED'
          ELSE 'OTHER'
        END AS bucket
      FROM library_files
      WHERE path LIKE '/Volumes/COMMUNE/%'
        AND lower(path) LIKE '%.flac'
    )
    GROUP BY bucket
    ORDER BY bucket;
  "
  echo

} | tee "${SUMMARY_LOG}"
