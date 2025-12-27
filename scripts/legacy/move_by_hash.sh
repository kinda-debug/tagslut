#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 DECISIONS_CSV QUARANTINE_ROOT" >&2
  exit 1
fi

DECISIONS_CSV=$1
QUAR_ROOT=$2

if [[ ! -f "$DECISIONS_CSV" ]]; then
  echo "ERROR: decisions CSV not found: $DECISIONS_CSV" >&2
  exit 1
fi

mkdir -p "$QUAR_ROOT"

echo "=== MOVE BY CSV ==="
echo "Decisions:   $DECISIONS_CSV"
echo "Quarantine:  $QUAR_ROOT"
echo

moved=0
skipped=0
missing=0

while IFS=',' read -r raw_path raw_action; do
  path="${raw_path%\"}"
  path="${path#\"}"
  action=$(echo "${raw_action%\"}" | tr '[:lower:]' '[:upper:]')

  [[ -z "$path" ]] && continue

  if [[ "$action" != "MOVE" ]]; then
    skipped=$((skipped + 1))
    continue
  fi

  if [[ ! -f "$path" ]]; then
    echo "MISSING: $path"
    missing=$((missing + 1))
    continue
  fi

  dest="$QUAR_ROOT$path"
  mkdir -p "$(dirname "$dest")"

  echo "MOVE: $path -> $dest"
  mv "$path" "$dest"
  moved=$((moved + 1))

done < <(awk -F',' 'NR>1{print $2","$3}' "$DECISIONS_CSV")

echo
echo "=== SUMMARY ==="
echo "Moved files:   $moved"
echo "Skipped rows:  $skipped"
echo "Missing files: $missing"
echo "================"
