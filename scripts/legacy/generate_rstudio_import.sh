#!/bin/bash
set -e

MANIFEST="artifacts/reports/per_volume/manifest_vault.csv"
OUTDIR="artifacts/recovery"
OUTCSV="$OUTDIR/rstudio_import_vault.csv"
RESTORE_ROOT="/Volumes/bad/RESTORED"

mkdir -p "$OUTDIR"

echo "source_path,destination_path" > "$OUTCSV"

tail -n +2 "$MANIFEST" | \
  awk -F',' -v root="$RESTORE_ROOT" '
    {
      gsub(/"/, "", $2);
      src=$2;

      # Remove leading slash if present
      sub(/^\/+/, "", src);

      # Build destination path
      dest=root "/" src;

      # Escape commas
      gsub(/,/, "_", dest);
      gsub(/,/, "_", src);

      print src "," dest;
    }
  ' >> "$OUTCSV"

echo "Generated: $OUTCSV"
