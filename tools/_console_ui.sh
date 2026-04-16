#!/usr/bin/env bash

ui_init() {
  UI_USE_COLOR=0
  if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    UI_USE_COLOR=1
  fi

  UI_CLR_RESET=$'\033[0m'
  UI_CLR_BOLD=$'\033[1m'
  UI_CLR_DIM=$'\033[2m'
  UI_CLR_RED=$'\033[31m'
  UI_CLR_GREEN=$'\033[32m'
  UI_CLR_YELLOW=$'\033[33m'
  UI_CLR_CYAN=$'\033[36m'
}

clr() {
  local code="$1"
  shift
  if [[ "${UI_USE_COLOR:-0}" -eq 1 ]]; then
    printf '%s%s%s' "$code" "$*" "$UI_CLR_RESET"
  else
    printf '%s' "$*"
  fi
}

ui_header() {
  local title="$1"
  printf '\n%s\n' "$(clr "${UI_CLR_BOLD:-}" "$title")"
}

ui_section() {
  local title="$1"
  printf '\n%s\n' "$(clr "${UI_CLR_CYAN:-}" "$title")"
}

ui_status() {
  local level="$1"
  shift
  local style="${UI_CLR_DIM:-}"
  case "$level" in
    ok|success) style="${UI_CLR_GREEN:-}" ;;
    warn|warning|skip|skipped) style="${UI_CLR_YELLOW:-}" ;;
    error|failed) style="${UI_CLR_RED:-}" ;;
    run|running) style="${UI_CLR_CYAN:-}" ;;
  esac
  printf '%s %s\n' "$(clr "$style" "[$(printf '%s' "$level" | tr '[:lower:]' '[:upper:]')]")" "$*"
}
