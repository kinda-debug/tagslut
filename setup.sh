#!/usr/bin/env bash

# setup.sh — Bootstrap environment and helper tasks for ChatGPT Copilot agent
# macOS (zsh) friendly; idempotent. Creates a Python venv, installs deps,
# verifies external tools, prepares artifacts dirs, and offers quick-run tasks.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

info()  { printf "[INFO] %s\n" "$*"; }
warn()  { printf "[WARN] %s\n" "$*"; }
error() { printf "[ERR ] %s\n" "$*" 1>&2; }

PY="python3"
PIP="pip"

ensure_python() {
  if ! command -v python3 >/dev/null 2>&1; then
    error "python3 not found — install Xcode CLT or Homebrew python"
    exit 1
  fi
}

create_venv() {
  if [[ ! -d "${VENV_DIR}" ]]; then
    info "Creating virtualenv at ${VENV_DIR}"
    "${PY}" -m venv "${VENV_DIR}"
  else
    info "Reusing existing venv ${VENV_DIR}"
  fi
}

activate_venv() {
  # shellcheck disable=SC1090
  source "${VENV_DIR}/bin/activate"
  PY="$(command -v python)"
  PIP="$(command -v pip)"
  info "Using Python: ${PY}"
}

install_deps() {
  if [[ -f "${ROOT_DIR}/requirements.txt" ]]; then
    info "Installing requirements.txt"
    "${PIP}" install -r "${ROOT_DIR}/requirements.txt"
  else
    info "No requirements.txt — installing minimal runtime deps"
    "${PIP}" install tqdm
  fi
}

verify_tools() {
  local missing=()
  for t in ffmpeg ffprobe fpcalc flac metaflac; do
    if ! command -v "$t" >/dev/null 2>&1; then
      missing+=("$t")
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    warn "Missing external tools: ${missing[*]}"
    warn "Install via Homebrew: brew install ffmpeg chromaprint flac"
  else
    info "External tools present"
  fi
}

prepare_artifacts() {
  mkdir -p "${ROOT_DIR}/artifacts/reports" "${ROOT_DIR}/artifacts/playlists"
}

print_help() {
  cat <<EOF
Usage: ./setup.sh [command]

Commands:
  env            Create venv, install dependencies, verify tools (default)
  scan-music     Run fast MD5 scan on /Volumes/dotad/MUSIC with watchdog
  scan-quar      Run fast MD5 scan on /Volumes/dotad/Quarantine with watchdog
  plan-moves     Generate dedupe move plan CSV from ~/.cache/file_dupes.db
  commit-moves   Execute planned moves (writes executed_moves.csv)
  prune-garbage  Delete duplicate losers inside Garbage (dry-run unless --commit)
  prune-cross    Delete all non-keeper duplicates across MUSIC+Quarantine+Garbage
  db-prune       Remove stale DB rows for missing files (default: under Garbage)
  help           Show this help

Environment:
  VENV: ${VENV_DIR}

EOF
}

run_scan() {
  local target="$1"
  local out_csv="$2"
  local hb="$3"
  info "Launching fast scan for ${target}"
  nohup "${PY}" "${ROOT_DIR}/scripts/find_dupes_fast.py" \
    "${target}" \
    --output "${out_csv}" \
    --heartbeat "${hb}" \
    --watchdog --watchdog-timeout 180 \
    > "/tmp/scan_$(basename "${target}").log" 2>&1 &
}

plan_moves() {
  "${PY}" "${ROOT_DIR}/scripts/dedupe_move_duplicates.py" \
    --db "${HOME}/.cache/file_dupes.db" \
    --report "${ROOT_DIR}/artifacts/reports/planned_moves.csv"
}

commit_moves() {
  "${PY}" "${ROOT_DIR}/scripts/dedupe_move_duplicates.py" \
    --db "${HOME}/.cache/file_dupes.db" \
    --commit \
    --report "${ROOT_DIR}/artifacts/reports/executed_moves.csv"
}

prune_garbage() {
  # Pass-through for extra args (e.g., --limit 100)
  # Decide report path based on presence of --commit in args
  local report
  local args=("$@")
  if printf '%s\n' "${args[@]}" | grep -q -- "^--commit$"; then
    report="${ROOT_DIR}/artifacts/reports/garbage_prune_executed.csv"
  else
    report="${ROOT_DIR}/artifacts/reports/garbage_prune_plan.csv"
  fi
  "${PY}" "${ROOT_DIR}/scripts/prune_garbage_duplicates.py" \
    --db "${HOME}/.cache/file_dupes.db" \
    --report "${report}" \
    "${args[@]}"
}

main() {
  local cmd="${1:-env}"
  case "${cmd}" in
    env)
      ensure_python
      create_venv
      activate_venv
      install_deps
      verify_tools
      prepare_artifacts
      info "Environment ready. Try: ./setup.sh scan-music"
      ;;
    scan-music)
      activate_venv || true
      run_scan \
        "/Volumes/dotad/MUSIC" \
        "/tmp/file_dupes_music.csv" \
        "/tmp/find_dupes_fast.music.hb"
      ;;
    scan-quar)
      activate_venv || true
      run_scan \
        "/Volumes/dotad/Quarantine" \
        "/tmp/file_dupes_quarantine.csv" \
        "/tmp/find_dupes_fast.quarantine.hb"
      ;;
    plan-moves)
      activate_venv || true
      plan_moves
      ;;
    commit-moves)
      activate_venv || true
      commit_moves
      ;;
    prune-garbage)
      activate_venv || true
      # Forward all args after the command, e.g., --commit --limit 100
      shift || true
      prune_garbage "$@"
      ;;
    prune-cross)
      activate_venv || true
      shift || true
      # Decide report name based on presence of --commit
      if printf '%s\n' "$@" | grep -q -- "^--commit$"; then
        report="${ROOT_DIR}/artifacts/reports/cross_root_prune_executed.csv"
      else
        report="${ROOT_DIR}/artifacts/reports/cross_root_prune_plan.csv"
      fi
      "${PY}" "${ROOT_DIR}/scripts/prune_cross_root_duplicates.py" \
        --db "${HOME}/.cache/file_dupes.db" \
        --report "${report}" \
        "$@"
      ;;
      db-prune)
        activate_venv || true
        shift || true
        "${PY}" "${ROOT_DIR}/scripts/db_prune_missing_files.py" "$@"
        ;;
    help|--help|-h)
      print_help
      ;;
    *)
      print_help
      error "Unknown command: ${cmd}"
      exit 2
      ;;
  esac
}

main "$@"
