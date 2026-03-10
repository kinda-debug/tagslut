#!/usr/bin/env bash
set -euo pipefail

declare -r REPO_ROOT="$(git rev-parse --show-toplevel)"
declare -r SCRIPT_DIR="$REPO_ROOT/tools/review"

declare -ra TARGETS=(
  "fix/migration-0006:MIGRATION_WT:fix/migration-0006"
  "fix/identity-service:IDENTITY_WT:fix/identity-service"
  "fix/backfill-v3:BACKFILL_WT:fix/dj-tag-enrichment"
)

resolve_worktree() {
  local branch=$1 envvar=$2
  local envpath="${!envvar:-}"
  if [[ -n "$envpath" ]]; then
    printf '%s' "$envpath"
    return 0
  fi

  git -C "$REPO_ROOT" worktree list --porcelain | \
    awk -v search="refs/heads/$branch" 'BEGIN { path = "" } /^worktree / { path = $2 } /^branch / && $2 == search { print path; exit }'
}

check_branch_sync() {
  local wt_path=$1 local_branch=$2 remote_branch=$3
  local local_ref="refs/heads/$local_branch"
  local remote_ref="refs/remotes/origin/$remote_branch"

  if ! git -C "$wt_path" show-ref --verify --quiet "$local_ref"; then
    printf 'error: local branch %s missing in %s\n' "$local_branch" "$wt_path" >&2
    exit 1
  fi

  if ! remote_hash=$(git -C "$wt_path" rev-parse "$remote_ref" 2>/dev/null); then
    printf 'remote %s not found; will push new history\n' "$remote_ref"
    return 0
  fi

  local local_hash
  local_hash=$(git -C "$wt_path" rev-parse "$local_ref")
  if [[ "$local_hash" == "$remote_hash" ]]; then
    return 1
  fi

  if git -C "$wt_path" merge-base --is-ancestor "$remote_ref" "$local_ref"; then
    printf '%s has new commits beyond %s\n' "$local_branch" "$remote_branch"
    return 0
  fi

  printf 'remote %s contains commits not present on %s; please reclone or merge manually\n' "$remote_branch" "$local_branch" >&2
  return 2
}

declare -A worktree_map=()
declare -a needs_sync=()
declare -a blocked=()

for entry in "${TARGETS[@]}"; do
  IFS=':' read -r branch envvar remote_branch <<<"$entry"
  wt_path=$(resolve_worktree "$branch" "$envvar")
  if [[ -z "$wt_path" ]]; then
    printf 'error: worktree for %s not found; set %s or create the worktree\n' "$branch" "$envvar" >&2
    exit 1
  fi

  worktree_map["$envvar"]=$wt_path

  status=$(check_branch_sync "$wt_path" "$branch" "$remote_branch")
  if [[ $status -eq 0 ]]; then
    needs_sync+=("$branch")
  elif [[ $status -eq 2 ]]; then
    blocked+=("$branch")
  fi
done

if [[ ${#blocked[@]} -gt 0 ]]; then
  printf 'aborted: remote divergence detected for %s\n' "${blocked[*]}" >&2
  exit 1
fi

if [[ ${#needs_sync[@]} -eq 0 ]]; then
  echo 'phase1 sync: all Phase 1 worktrees already match their upstream branches'
  exit 0
fi

echo 'phase1 sync: detected updates for' "${needs_sync[*]}"
MIGRATION_WT="${worktree_map[MIGRATION_WT]}" \
IDENTITY_WT="${worktree_map[IDENTITY_WT]}" \
BACKFILL_WT="${worktree_map[BACKFILL_WT]}" \
"$SCRIPT_DIR/sync_phase1_prs.sh"
