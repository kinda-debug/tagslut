#!/bin/bash
echo "=== COMMUNE Big Move - Thunderbolt Mode ==="
echo "Started: $(date)"

echo -e "\n1. Moving _quarantine__2026-01-14 (857 GB)..."
time rsync -av --progress \
  /Volumes/COMMUNE/M/_quarantine__2026-01-14/ \
  /Volumes/bad/_commune_quarantine_2026-01-14_FINAL/

echo -e "\nVerifying counts..."
src=$(find /Volumes/COMMUNE/M/_quarantine__2026-01-14 -type f 2>/dev/null | wc -l)
dst=$(find /Volumes/bad/_commune_quarantine_2026-01-14_FINAL -type f 2>/dev/null | wc -l)

if [ "$src" -eq "$dst" ]; then
    echo "✓ Counts match - deleting source"
    rm -rf /Volumes/COMMUNE/M/_quarantine__2026-01-14
    echo "✓ Freed ~857 GB"
else
    echo "⚠️  Mismatch: src=$src dst=$dst"
    echo "NOT deleting source"
fi

echo -e "\nFinal status:"
df -h /Volumes/COMMUNE

echo "Completed: $(date)"
