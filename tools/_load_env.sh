#!/usr/bin/env bash

load_workspace_env() {
  local repo_root="$1"
  local env_file="${repo_root}/.env"

  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
}
