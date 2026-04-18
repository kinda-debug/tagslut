#!/usr/bin/env bash

ts_wrapper_bootstrap() {
  local script_path="${1:?script path is required}"

  TAGSLUT_TOOLS_DIR="$(cd "$(dirname "$script_path")" && pwd)"
  TAGSLUT_REPO_ROOT="$(cd "${TAGSLUT_TOOLS_DIR}/.." && pwd)"

  local env_loader="${TAGSLUT_TOOLS_DIR}/_load_env.sh"
  if [[ -f "$env_loader" ]]; then
    # shellcheck disable=SC1090
    source "$env_loader"
    load_workspace_env "$TAGSLUT_REPO_ROOT"
  fi
}

ts_repo_python() {
  if [[ -n "${TAGSLUT_REPO_ROOT:-}" && -x "${TAGSLUT_REPO_ROOT}/.venv/bin/python" ]]; then
    printf '%s\n' "${TAGSLUT_REPO_ROOT}/.venv/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  printf '%s\n' "Error: python is not available" >&2
  return 1
}

ts_die() {
  printf '%s\n' "Error: $*" >&2
  exit 1
}
