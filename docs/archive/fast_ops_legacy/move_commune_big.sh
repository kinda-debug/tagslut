#!/bin/bash
# NOTE: This script uses hardcoded paths and should be migrated to use environment variables
# Load .env if available
if [ -f "$(dirname "$0")/../.env" ]; then
    export $(grep -v '^#' "$(dirname "$0")/../.env" | xargs)
fi

echo "=== COMMUNE Big Move - Thunderbolt Mode ==="
echo "Started: $(date)"

# Use env variables with fallback to hardcoded paths
QUARANTINE_SRC="${VOLUME_QUARANTINE:-/Volumes/COMMUNE/M/_quarantine__2026-01-14}"
BAD_VOLUME="${VOLUME_BAD:-/Volumes/bad}"

echo -e "\n1. Moving quarantine directory..."
time rsync -av --progress \
  "$QUARANTINE_SRC/" \
  "$BAD_VOLUME/_commune_quarantine_2026-01-14_FINAL/"

echo -e "\nVerifying counts..."
src=$(find "$QUARANTINE_SRC" -type f 2>/dev/null | wc -l)
dst=$(find "$BAD_VOLUME/_commune_quarantine_2026-01-14_FINAL" -type f 2>/dev/null | wc -l)

if [ "$src" -eq "$dst" ]; then
    echo "✓ Counts match - deleting source"
    rm -rf "$QUARANTINE_SRC"
    echo "✓ Freed ~857 GB"
else
    echo "⚠️  Mismatch: src=$src dst=$dst"
    echo "NOT deleting source"
fi

echo -e "\nFinal status:"
df -h "${VOLUME_LIBRARY:-/Volumes/COMMUNE}"

echo "Completed: $(date)"
