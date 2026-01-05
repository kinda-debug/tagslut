#!/usr/bin/env bash
# Script to archive and clean up scripts in dedupe_repo_reclone
set -euo pipefail

ARCHIVE_DIR="$HOME/dedupe_repo_reclone/ARCHIVE_SCRIPTS"
mkdir -p "$ARCHIVE_DIR"

# Archive legacy/obsolete scripts
mv "$HOME/dedupe_repo_reclone/artifacts/reports/move_to_rejected.sh" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$HOME/dedupe_repo_reclone/artifacts/reports/dry_run_delete.sh" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$HOME/dedupe_repo_reclone/test_nohup.sh" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$HOME/dedupe_repo_reclone/pipefail.sh" "$ARCHIVE_DIR/" 2>/dev/null || true

# Archive all scripts in legacy and ARCHIVE folders
find "$HOME/dedupe_repo_reclone/archive/legacy_root" -type f -name "*.sh" -exec mv {} "$ARCHIVE_DIR/" \;
find "$HOME/dedupe_repo_reclone/dedupe/ARCHIVE" -type f -name "*.sh" -exec mv {} "$ARCHIVE_DIR/" \;

# Archive redundant export scripts (keep best, archive rest)
mv "$HOME/dedupe_repo_reclone/export_canonical_plus_unique.sh" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$HOME/dedupe_repo_reclone/export_canonical_and_rescan.sh" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$HOME/dedupe_repo_reclone/build_export_and_rescan.sh" "$ARCHIVE_DIR/" 2>/dev/null || true
mv "$HOME/dedupe_repo_reclone/full_canonical_rebuild_and_export.sh" "$ARCHIVE_DIR/" 2>/dev/null || true

# Optionally delete broken/unused scripts
# rm "$HOME/dedupe_repo_reclone/test_nohup.sh" "$HOME/dedupe_repo_reclone/pipefail.sh" 2>/dev/null || true

# Log summary
ls -lh "$ARCHIVE_DIR" > "$ARCHIVE_DIR/README.md"
echo "Scripts archived on $(date)" >> "$ARCHIVE_DIR/README.md"
