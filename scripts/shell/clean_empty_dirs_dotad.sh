#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/Volumes/dotad}"
REPO="${HOME}/dedupe_repo_reclone"
LOG_DIR="${REPO}/artifacts/logs"

mkdir -p "${LOG_DIR}"

ts="$(date +'%Y%m%d_%H%M%S')"
LOG_FILE="${LOG_DIR}/cleanup_empty_dirs_dotad_${ts}.log"

echo "=== CLEAN EMPTY DIRECTORIES ON: ${ROOT} ==="
echo "Log: ${LOG_FILE}"
echo

if [[ ! -d "${ROOT}" ]]; then
  echo "ERROR: Root directory does not exist: ${ROOT}"
  exit 1
fi

# Dry list of empty directories (without deleting yet)
echo "=== Scanning for empty directories (dry list) ==="
find "${ROOT}" -mindepth 1 -type d -empty | sort > "${LOG_FILE}"
count_listed=$(wc -l < "${LOG_FILE}" | tr -d ' ')
echo "Empty directories found: ${count_listed}"
echo

if [[ "${count_listed}" -eq 0 ]]; then
  echo "No empty directories to remove."
  exit 0
fi

echo "=== Removing empty directories (deepest-first) ==="

# Remove deepest first to avoid parent-directory order issues
# We re-read from the log to ensure the same set is processed.
removed=0
while IFS= read -r dir; do
  [[ -z "${dir}" ]] && continue
  if rmdir "${dir}" 2>/dev/null; then
    echo "REMOVED: ${dir}"
    ((removed++))
  fi
done < <(sort -r "${LOG_FILE}")

echo
echo "Summary:"
echo "  Listed empty dirs: ${count_listed}"
echo "  Removed dirs:      ${removed}"
echo "  Log file:          ${LOG_FILE}"
