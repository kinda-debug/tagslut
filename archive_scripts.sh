#!/bin/bash
# Archive diagnostic and experimental scripts

ARCHIVE_DIR="archive/scripts_diagnostic_2025"
mkdir -p "$ARCHIVE_DIR"

echo "Archiving diagnostic and experimental scripts..."

# Diagnostic scripts (one-off tools)
mv scripts/check_schema.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/verify_json_metadata.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/show_scan_status.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/migrate_metadata_schema.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/check_truncation.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/rank_duration_deltas.py "$ARCHIVE_DIR/" 2>/dev/null

# Experimental/superseded scripts
mv scripts/find_dupes_fast_v2.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/find_exact_dupes.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/find_content_dupes.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/fast_inspect_paths.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/inspect_paths.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/start_scan.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/dedupe_repaired_sizefirst.py "$ARCHIVE_DIR/" 2>/dev/null

# Potentially obsolete (check if used)
mv scripts/file_operations.py "$ARCHIVE_DIR/" 2>/dev/null
mv scripts/validate_repair_with_acoustid.py "$ARCHIVE_DIR/" 2>/dev/null

echo "Archive complete! Files moved to $ARCHIVE_DIR/"
ls -1 "$ARCHIVE_DIR/"
