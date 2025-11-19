#!/usr/bin/env bash
set -euo pipefail

ROOT="artifacts/db"

echo "=== SCANNING FOR DUPLICATE SQLITE DATABASES ==="
mapfile -t files < <(find "$ROOT" -type f \( -name "*.db" -o -name "*.sqlite" \))

if [[ ${#files[@]} -eq 0 ]]; then
  echo "No .db or .sqlite files found. Nothing to do."
  exit 0
fi

declare -A newest_path
declare -A newest_mtime
declare -A newest_size

# Collect all DBs by basename
for f in "${files[@]}"; do
  bn=$(basename "$f")
  mt=$(stat -f "%m" "$f")
  sz=$(stat -f "%z" "$f")

  # If first time seeing this DB name → mark as newest
  if [[ -z "${newest_mtime[$bn]:-}" ]]; then
    newest_path[$bn]="$f"
    newest_mtime[$bn]="$mt"
    newest_size[$bn]="$sz"
    continue
  fi

  # If newer copy exists → replace stored newest
  if (( mt > newest_mtime[$bn] )); then
    newest_path[$bn]="$f"
    newest_mtime[$bn]="$mt"
    newest_size[$bn]="$sz"
  fi
done

echo "=== REMOVING STALE DUPLICATES ==="
removed_any=false
for f in "${files[@]}"; do
  bn=$(basename "$f")
  if [[ "$f" != "${newest_path[$bn]}" ]]; then
    echo "Deleting stale duplicate: $f"
    rm -f "$f"
    removed_any=true
  fi
done

if ! $removed_any; then
  echo "No stale duplicates found."
fi

echo "=== FINAL LIST OF KEPT DATABASES ==="
for bn in "${!newest_path[@]}"; do
  echo "$bn --> ${newest_path[$bn]}"
done

echo "Cleanup complete."
