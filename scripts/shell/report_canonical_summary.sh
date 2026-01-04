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
  dotad_flac=$(sqlite3 "${CANON_DB}" "
    SELECT COUNT(*)
    FROM library_files
    WHERE path LIKE '/Volumes/dotad/%' AND lower(path) LIKE '%.flac';
  ")
  bad_flac=$(sqlite3 "${CANON_DB}" "
    SELECT COUNT(*)
    FROM library_files
    WHERE path LIKE '/Volumes/bad/%' AND lower(path) LIKE '%.flac';
  ")
  other_flac=$(sqlite3 "${CANON_DB}" "
    SELECT COUNT(*)
    FROM library_files
    WHERE path NOT LIKE '/Volumes/dotad/%'
      AND path NOT LIKE '/Volumes/bad/%'
      AND lower(path) LIKE '%.flac';
  ")

  echo "  Total canonical FLAC tracks : ${total_flac}"
  echo "  On /Volumes/dotad           : ${dotad_flac}"
  echo "  On /Volumes/bad             : ${bad_flac}"
  echo "  On other volumes            : ${other_flac}"
  echo

  echo "2) Dotad canonical FLACs by top-level bucket:"
  sqlite3 "${CANON_DB}" "
    SELECT bucket, COUNT(*) AS count
    FROM (
      SELECT
        CASE
          WHEN path LIKE '/Volumes/dotad/MUSIC/%' THEN 'MUSIC'
          WHEN path LIKE '/Volumes/dotad/RECOVERED_FROM_MISSING/%' THEN 'RECOVERED_FROM_MISSING'
          WHEN path LIKE '/Volumes/dotad/G_DUPEGURU/%' THEN 'G_DUPEGURU'
          WHEN path LIKE '/Volumes/dotad/NEW_LIBRARY_CLEAN/%' THEN 'NEW_LIBRARY_CLEAN'
          WHEN path LIKE '/Volumes/dotad/QUARANTINE_AUTO_GLOBAL/%' THEN 'QUARANTINE_AUTO_GLOBAL'
          ELSE 'OTHER_DOTAD'
        END AS bucket
      FROM library_files
      WHERE path LIKE '/Volumes/dotad/%'
        AND lower(path) LIKE '%.flac'
    )
    GROUP BY bucket
    ORDER BY bucket;
  "
  echo

  echo "3) Bad canonical FLACs by top-level bucket:"
  sqlite3 "${CANON_DB}" "
    SELECT bucket, COUNT(*) AS count
    FROM (
      SELECT
        CASE
          WHEN path LIKE '/Volumes/bad/FINAL_LIBRARY/%' THEN 'FINAL_LIBRARY'
          WHEN path LIKE '/Volumes/bad/DOTAD_DEDUPED/%' THEN 'DOTAD_DEDUPED'
          ELSE 'OTHER_BAD'
        END AS bucket
      FROM library_files
      WHERE path LIKE '/Volumes/bad/%'
        AND lower(path) LIKE '%.flac'
    )
    GROUP BY bucket
    ORDER BY bucket;
  "
  echo

} | tee "${SUMMARY_LOG}"
