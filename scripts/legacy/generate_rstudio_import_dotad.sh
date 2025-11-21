#!/usr/bin/env bash
set -euo pipefail

MANIFEST="artifacts/reports/per_volume/manifest_dotad.csv"
OUTCSV="artifacts/recovery/rstudio_import_dotad.csv"
RESTORE_ROOT="/Volumes/sad/RESTORED"

if [ ! -f "$MANIFEST" ]; then
    echo "ERROR: Manifest not found: $MANIFEST"
    exit 1
fi

mkdir -p "$(dirname "$OUTCSV")"
mkdir -p "$RESTORE_ROOT"

echo "source_path,destination_path" > "$OUTCSV"

tail -n +2 "$MANIFEST" | \
  awk -F',' -v root="$RESTORE_ROOT" '
    {
      # Clean quotes
      gsub(/"/, "", $2)

      src=$2

      if (src == "" || src ~ /^ *$/) next

      # Strip leading slashes
      sub(/^\/+/, "", src)

      # Construct destination
      dest = root "/" src

      # Replace commas to avoid CSV breakage
      gsub(/,/, "_", src)
      gsub(/,/, "_", dest)

      print src "," dest
    }
  ' >> "$OUTCSV"

echo "Generated: $OUTCSV"
