#!/usr/bin/env bash
set -euo pipefail

# Sync Phase 1 stacked branches to origin while preserving PR scope boundaries.
#
# This script intentionally keeps `fix/v3-backfill-command` (PR #186 scope)
# separate from DJ tag enrichment work. DJ enrichment is pushed to
# `fix/dj-tag-enrichment` from a local `fix/backfill-v3` worktree.

MIGRATION_WT="${MIGRATION_WT:-/tmp/tagslut_wt_migration}"
IDENTITY_WT="${IDENTITY_WT:-/tmp/tagslut_wt_identity}"
BACKFILL_WT="${BACKFILL_WT:-/tmp/tagslut_wt_backfill}"

for wt in "$MIGRATION_WT" "$IDENTITY_WT" "$BACKFILL_WT"; do
  if [[ ! -d "$wt/.git" && ! -f "$wt/.git" ]]; then
    echo "missing worktree: $wt" >&2
    exit 1
  fi
done

run_push() {
  local repo_path="$1"
  shift
  echo "+ git -C $repo_path push $*"
  git -C "$repo_path" push "$@"
}

# 1) migration stack update (PR #193)
run_push "$MIGRATION_WT" origin fix/migration-0006 --force-with-lease

# 2) identity service update (PR #185)
run_push "$IDENTITY_WT" origin fix/identity-service --force-with-lease

# 3) DJ enrichment as its own branch; do NOT reuse fix/v3-backfill-command.
run_push "$BACKFILL_WT" origin fix/backfill-v3:fix/dj-tag-enrichment --force-with-lease

echo "done: pushed migration, identity, and dj enrichment branches"

echo ""
echo "next: open DJ enrichment draft PR:"
echo "  gh pr create --base fix/identity-service --head fix/dj-tag-enrichment \\"
echo "    --title 'feat(dj): enrich FLAC DJ tags from v3 identity cache before transcode' \\"
echo "    --draft"
