#!/usr/bin/env zsh
set -euo pipefail

# Restore files listed in artifacts/reports/garbage_backup_restore_plan.tsv
# Format: <source_path>\t<dest_path>

PLAN="${1:-artifacts/reports/garbage_backup_restore_plan.tsv}"

if [[ ! -f "$PLAN" ]]; then
  echo "Restore plan not found: $PLAN" >&2
  exit 1
fi

echo "Restoring files from plan: $PLAN"
echo "This will copy files into /Volumes/dotad/NEW_LIBRARY/Garbage_backup"

while IFS=$'\t' read -r src dest; do
  [[ -z "$src" ]] && continue
  if [[ ! -f "$src" ]]; then
    echo "[SKIP] Missing source: $src" >&2
    continue
  fi
  mkdir -p "$(dirname "$dest")"
  rsync -a --inplace --no-perms --no-owner --no-group "$src" "$dest"
  echo "[OK] $src -> $dest"
done < "$PLAN"

echo "Done."
