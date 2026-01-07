#!/usr/bin/env bash
set -euo pipefail

require_db_value() {
  local value="$1"
  local label="$2"
  if [[ -z "$value" ]]; then
    echo "Error: $label is required (set $label or DEDUPE_DB)." >&2
    exit 1
  fi
  echo "$value"
}

resolve_db_path() {
  local purpose="$1"
  local db_path="$2"
  local create_flag="${3:-}"
  local allow_repo_flag="${4:-}"
  local cmd=(python3 "$REPO/tools/db/resolve_db_path.py" --purpose "$purpose" --print-path)
  if [[ -n "$db_path" ]]; then
    cmd+=(--db "$db_path")
  fi
  if [[ -n "${ALLOW_REPO_DB:-}" || -n "$allow_repo_flag" ]]; then
    cmd+=(--allow-repo-db)
  fi
  if [[ -n "${CREATE_DB:-}" || -n "$create_flag" ]]; then
    cmd+=(--create-db)
  fi
  "${cmd[@]}"
}
