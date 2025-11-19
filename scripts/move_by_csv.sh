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

echo "=== MOVE BY CSV (SAFE MODE) ==="
echo "Decisions:   $DECISIONS_CSV"
echo "Quarantine:  $QUAR_ROOT"
echo

moved=0
skipped=0
missing=0

# Read line-by-line WITHOUT piping (avoids subshell)
{
  read -r header   # skip CSV header
  while IFS= read -r line || [[ -n "$line" ]]; do

    # Extract first two fields only: path, action
    # using AWK internally while staying in this shell.
    parsed="$(printf '%s\n' "$line" | awk -F',' '{
      path=$1
      action=$2
      print path "|" action
    }')"

    path="${parsed%%|*}"
    raw_action="${parsed##*|}"

    # Remove surrounding quotes from path
    path="${path%\"}"
    path="${path#\"}"

    # Manual whitespace trim (no xargs)
    path="$(printf '%s' "$path" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    action="${raw_action%\"}"
    action="${action#\"}"
    action="$(printf '%s' "$action" | tr '[:lower:]' '[:upper:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    [[ -z "$path" ]] && continue

    if [[ "$action" != "MOVE" ]]; then
      skipped=$((skipped+1))
      continue
    fi

    if [[ ! -f "$path" ]]; then
      echo "MISSING: $path"
      missing=$((missing+1))
      continue
    fi

    dest="$QUAR_ROOT$path"
    dest_dir="$(dirname "$dest")"
    mkdir -p "$dest_dir"

    if [[ -f "$dest" ]]; then
      echo "SKIP (exists): $path"
      skipped=$((skipped+1))
      continue
    fi

    echo "MOVE: $path → $dest"
    mv "$path" "$dest"
    moved=$((moved+1))

  done
} < "$DECISIONS_CSV"

echo
echo "=== SUMMARY ==="
echo "Moved files:   $moved"
echo "Skipped rows:  $skipped"
echo "Missing files: $missing"
echo "================"