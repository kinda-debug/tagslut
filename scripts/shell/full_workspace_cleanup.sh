#!/usr/bin/env bash
# Comprehensive cleanup and archiving for dedupe_repo_reclone
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARCHIVE_SCRIPTS="$REPO/ARCHIVE_SCRIPTS"
ARCHIVE_DOCS="$REPO/ARCHIVE_DOCS"
ARCHIVE_LOGS="$REPO/ARCHIVE_LOGS"
ARCHIVE_DBS="$REPO/ARCHIVE_DBS"
DB_DIR="${DB_DIR:-}"

if [[ -z "$DB_DIR" ]]; then
  echo "Error: DB_DIR is required." >&2
  exit 1
fi

mkdir -p "$ARCHIVE_SCRIPTS" "$ARCHIVE_DOCS" "$ARCHIVE_LOGS" "$ARCHIVE_DBS"

# Archive all .sh and .py scripts from legacy, archive, and redundant locations
find "$REPO" \( -path "*/ARCHIVE*" -o -path "*/legacy*" -o -path "*/artifacts/reports*" \) -type f \( -name "*.sh" -o -name "*.py" \) -exec mv -v {} "$ARCHIVE_SCRIPTS/" \; 2>&1 | tee -a "$ARCHIVE_SCRIPTS/README.md"

# Archive outdated documentation
find "$REPO/docs" \( -path "*/ARCHIVE*" -o -name "*legacy*" -o -name "*old*" \) -type f -exec mv -v {} "$ARCHIVE_DOCS/" \; 2>&1 | tee -a "$ARCHIVE_DOCS/README.md"

# Archive old logs (older than 60 days)
find "$REPO/artifacts/logs" -type f -mtime +60 -exec mv -v {} "$ARCHIVE_LOGS/" \; 2>&1 | tee -a "$ARCHIVE_LOGS/README.md"

# Archive old databases (not library_canonical_fresh.db)
find "$DB_DIR" -type f \( -name "*.db" -and ! -name "library_canonical_fresh.db" \) -exec mv -v {} "$ARCHIVE_DBS/" \; 2>&1 | tee -a "$ARCHIVE_DBS/README.md"

# Log completion
for d in "$ARCHIVE_SCRIPTS" "$ARCHIVE_DOCS" "$ARCHIVE_LOGS" "$ARCHIVE_DBS"; do
  echo "Archived files in $d on $(date)" >> "$d/README.md"
done
