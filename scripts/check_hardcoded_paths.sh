#!/usr/bin/env bash
set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: must run inside a git repository"
  exit 2
fi

allow_archive="${ALLOW_ARCHIVE_DOCS:-1}"
patterns=("/Users/" "tagslut_db/EPOCH")

pathspec=(":(exclude).git")
pathspec+=(":(exclude)scripts/check_hardcoded_paths.sh")
pathspec+=(":(exclude)tools/archive/**")
pathspec+=(":(exclude)config/dj/playlists/**")
if [[ "$allow_archive" == "1" ]]; then
  pathspec+=(":(exclude)docs/archive/**")
fi

failed=0
for pattern in "${patterns[@]}"; do
  if git grep -n -- "$pattern" -- . "${pathspec[@]}"; then
    echo "ERROR: found forbidden hardcoded path pattern: $pattern"
    failed=1
  fi
done

if [[ $failed -ne 0 ]]; then
  exit 1
fi

echo "OK: no forbidden hardcoded path patterns found in tracked files"
