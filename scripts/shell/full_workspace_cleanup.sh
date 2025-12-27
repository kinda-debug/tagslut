#!/usr/bin/env bash
# Comprehensive cleanup and archiving for dedupe_repo_reclone
set -euo pipefail

ARCHIVE_SCRIPTS="$HOME/dedupe_repo_reclone/ARCHIVE_SCRIPTS"
ARCHIVE_DOCS="$HOME/dedupe_repo_reclone/ARCHIVE_DOCS"
ARCHIVE_LOGS="$HOME/dedupe_repo_reclone/ARCHIVE_LOGS"
ARCHIVE_DBS="$HOME/dedupe_repo_reclone/ARCHIVE_DBS"

mkdir -p "$ARCHIVE_SCRIPTS" "$ARCHIVE_DOCS" "$ARCHIVE_LOGS" "$ARCHIVE_DBS"

# Archive all .sh and .py scripts from legacy, archive, and redundant locations
find "$HOME/dedupe_repo_reclone" \( -path "*/ARCHIVE*" -o -path "*/legacy*" -o -path "*/artifacts/reports*" \) -type f \( -name "*.sh" -o -name "*.py" \) -exec mv -v {} "$ARCHIVE_SCRIPTS/" \; 2>&1 | tee -a "$ARCHIVE_SCRIPTS/README.md"

# Archive outdated documentation
find "$HOME/dedupe_repo_reclone/docs" \( -path "*/ARCHIVE*" -o -name "*legacy*" -o -name "*old*" \) -type f -exec mv -v {} "$ARCHIVE_DOCS/" \; 2>&1 | tee -a "$ARCHIVE_DOCS/README.md"

# Archive old logs (older than 60 days)
find "$HOME/dedupe_repo_reclone/artifacts/logs" -type f -mtime +60 -exec mv -v {} "$ARCHIVE_LOGS/" \; 2>&1 | tee -a "$ARCHIVE_LOGS/README.md"

# Archive old databases (not library_canonical_fresh.db)
find "$HOME/dedupe_repo_reclone/artifacts/db" -type f \( -name "*.db" -and ! -name "library_canonical_fresh.db" \) -exec mv -v {} "$ARCHIVE_DBS/" \; 2>&1 | tee -a "$ARCHIVE_DBS/README.md"

# Log completion
for d in "$ARCHIVE_SCRIPTS" "$ARCHIVE_DOCS" "$ARCHIVE_LOGS" "$ARCHIVE_DBS"; do
  echo "Archived files in $d on $(date)" >> "$d/README.md"
done
