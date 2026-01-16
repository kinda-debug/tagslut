#!/bin/bash
set -e

echo "========================================================================"
echo "BAD VOLUME CONSOLIDATION"
echo "========================================================================"
echo ""
echo "This will create a clean 2-folder structure:"
echo ""
echo "  /Volumes/bad/"
echo "    ├── archive/          (Long-term storage)"
echo "    └── quarantine/       (Temporary, delete after review)"
echo ""
echo "Proposed moves:"
echo "  → archive/R/              (104 GB - music archive)"
echo "  → archive/G/              (18 GB - additional content)"
echo "  → archive/backups/        (55 GB - Roon backups)"
echo ""
echo "  → quarantine/2026-01-15/  (7.5 GB - today's cleanup)"
echo "  → quarantine/old/         (All other dirs)"
echo ""
echo "WILL DELETE (old dedup work - obsolete):"
echo "  → bad_to_scan/           (108 GB) - old recovery session"
echo "  → _vault_lost_password/  (43 GB) - old recovery"
echo "  → dedupe_archives/       (11 GB) - old dedupe work"
echo ""
echo "Total space to free: ~162 GB"
echo ""
read -p "Continue? (type 'yes' to confirm): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

cd /Volumes/bad

# Create new structure
echo ""
echo "Creating directory structure..."
mkdir -p archive/{music,backups}
mkdir -p quarantine/{2026-01-15,old}

# Move archive content
echo "Moving archive content..."
mv R/ archive/music/R/ 2>/dev/null || true
mv G/ archive/music/G/ 2>/dev/null || true
mv RoonBackups/ archive/backups/ 2>/dev/null || true
mv RoonBackups_icloud/ archive/backups/ 2>/dev/null || true

# Move recent quarantines
echo "Moving recent quarantines..."
mv _auto_quarantine_20260115/ quarantine/2026-01-15/ 2>/dev/null || true
mv _final_cleanup_20260115/ quarantine/2026-01-15/ 2>/dev/null || true

# Move old quarantines
echo "Moving old quarantines..."
mv COMMUNE_offload_2026-01-14/ quarantine/old/ 2>/dev/null || true
mv _commune_archive_20260109/ quarantine/old/ 2>/dev/null || true
mv _AAC/ quarantine/old/ 2>/dev/null || true
mv _STAGING_ARCHIVE/ quarantine/old/ 2>/dev/null || true
mv library_exports/ quarantine/old/ 2>/dev/null || true
mv DEDUPER_RESCAN/ quarantine/old/ 2>/dev/null || true

# DELETE obsolete recovery/dedup work
echo ""
echo "Deleting obsolete files..."
rm -rf bad_to_scan/              # 108 GB - old dedup session
rm -rf _vault_lost_password_dmg/  # 43 GB - old recovery
rm -rf dedupe_archives/          # 11 GB - old dedupe work

echo ""
echo "✓ Consolidation complete!"
echo ""
du -sh /Volumes/bad/archive/
du -sh /Volumes/bad/quarantine/
echo ""
echo "Next: Delete quarantine/old/ when ready (after review period)"
