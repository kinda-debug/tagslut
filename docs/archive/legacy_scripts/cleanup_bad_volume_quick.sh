#!/bin/bash
set -e

echo "========================================================================"
echo "BAD VOLUME - QUICK CLEANUP (Old Quarantine Directories)"
echo "========================================================================"
echo ""
echo "This will DELETE these directories:"
echo "  /Volumes/bad/_vault_quarantine (801 files, ~3.4 GB)"
echo "  /Volumes/bad/_commune_quarantine (149 files, ~0.5 GB)"
echo ""
echo "These are old cleanup sessions. Total space freed: ~3.9 GB"
echo ""
read -p "Continue? (type 'yes' to confirm): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Deleting _vault_quarantine..."
rm -rf /Volumes/bad/_vault_quarantine

echo "Deleting _commune_quarantine..."
rm -rf /Volumes/bad/_commune_quarantine

echo ""
echo "✓ Old quarantine directories deleted!"
echo "✓ Space freed: ~3.9 GB"
echo ""
echo "Next: Run deduplicate script for R/ directory"
