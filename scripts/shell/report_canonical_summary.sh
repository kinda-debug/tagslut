#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$REPO/scripts/shell/_resolve_db_path.sh"

CANON_DB="${CANON_DB:-}"
LOG_DIR="${LOG_DIR:-$REPO/artifacts/logs}"
COMMUNE_ACCEPTED="${COMMUNE_ACCEPTED:-}"
COMMUNE_STAGING="${COMMUNE_STAGING:-}"
COMMUNE_REJECTED="${COMMUNE_REJECTED:-}"

CANON_DB="$(require_db_value "$CANON_DB" "CANON_DB")"
COMMUNE_ACCEPTED="$(require_db_value "$COMMUNE_ACCEPTED" "COMMUNE_ACCEPTED")"
COMMUNE_STAGING="$(require_db_value "$COMMUNE_STAGING" "COMMUNE_STAGING")"
COMMUNE_REJECTED="$(require_db_value "$COMMUNE_REJECTED" "COMMUNE_REJECTED")"
CANON_DB="$(resolve_db_path "read" "$CANON_DB")"

mkdir -p "${LOG_DIR}"

ts="$(date +'%Y%m%d_%H%M%S')"
SUMMARY_LOG="${LOG_DIR}/canonical_summary_${ts}.log"

echo "=== CANONICAL LIBRARY SUMMARY ==="
echo "CANON DB : ${CANON_DB}"
echo "LOG FILE : ${SUMMARY_LOG}"
echo

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
    WHERE path LIKE '${COMMUNE_ACCEPTED}/%' AND lower(path) LIKE '%.flac';
  ")
  staging_flac=$(sqlite3 "${CANON_DB}" "
    SELECT COUNT(*)
    FROM library_files
    WHERE path LIKE '${COMMUNE_STAGING}/%' AND lower(path) LIKE '%.flac';
  ")
  rejected_flac=$(sqlite3 "${CANON_DB}" "
    SELECT COUNT(*)
    FROM library_files
    WHERE path LIKE '${COMMUNE_REJECTED}/%' AND lower(path) LIKE '%.flac';
  ")
  other_flac=$(sqlite3 "${CANON_DB}" "
    SELECT COUNT(*)
    FROM library_files
    WHERE path NOT LIKE '${COMMUNE_ACCEPTED}/%'
      AND path NOT LIKE '${COMMUNE_STAGING}/%'
      AND path NOT LIKE '${COMMUNE_REJECTED}/%'
      AND lower(path) LIKE '%.flac';
  ")

  echo "  Total canonical FLAC tracks : ${total_flac}"
  echo "  On ${COMMUNE_ACCEPTED} : ${accepted_flac}"
  echo "  On ${COMMUNE_STAGING}  : ${staging_flac}"
  echo "  On ${COMMUNE_REJECTED} : ${rejected_flac}"
  echo "  On other volumes            : ${other_flac}"
  echo

  echo "2) COMMUNE canonical FLACs by zone:"
  sqlite3 "${CANON_DB}" "
    SELECT bucket, COUNT(*) AS count
    FROM (
      SELECT
        CASE
          WHEN path LIKE '${COMMUNE_ACCEPTED}/%' THEN 'ACCEPTED'
          WHEN path LIKE '${COMMUNE_STAGING}/%' THEN 'STAGING'
          WHEN path LIKE '${COMMUNE_REJECTED}/%' THEN 'REJECTED'
          ELSE 'OTHER'
        END AS bucket
      FROM library_files
      WHERE path LIKE '$(dirname "${COMMUNE_ACCEPTED}")/%'
        AND lower(path) LIKE '%.flac'
    )
    GROUP BY bucket
    ORDER BY bucket;
  "
  echo

} | tee "${SUMMARY_LOG}"
