# Script Consolidation Summary

**Date**: November 12, 2025

## Changes Made

### 1. Scripts Merged

**`dedupe_repaired.py`** (Consolidated)
- Merged `dedupe_repaired_sizefirst.py` functionality
- Now supports both modes via `--fast` flag:
  - Normal mode: Comprehensive scan of all files
  - Fast mode: Size-first optimization (recommended for large trees)
- Improved keeper selection (prefers paths without `.repaired` suffix)
- Better error handling and progress reporting

### 2. Scripts Archived

Moved to `archive/scripts_diagnostic_2025/`:

**Diagnostic/One-time:**
- `check_schema.py` - DB schema checker (temp diagnostic)
- `verify_json_metadata.py` - JSON storage verification (temp)
- `show_scan_status.py` - Scan progress checker (temp)
- `migrate_metadata_schema.py` - One-time migration (completed)
- `check_truncation.py` - Diagnostic tool
- `rank_duration_deltas.py` - One-off analysis
- `start_scan.py` - Unclear purpose

**Experimental/Superseded:**
- `find_dupes_fast_v2.py` - File-based cache (SQLite version is better)
- `find_exact_dupes.py` - Audio-MD5 scanner (superseded by flac_scan.py)
- `find_content_dupes.py` - PCM SHA1 comparison (limited use case)
- `dedupe_repaired_sizefirst.py` - Merged into dedupe_repaired.py
- `fast_inspect_paths.py` - Experimental
- `inspect_paths.py` - Experimental
- `file_operations.py` - Generic helpers (check if unused)
- `validate_repair_with_acoustid.py` - Experimental AcoustID

### 3. Core Production Scripts (Retained)

**Duplicate Detection:**
- `find_dupes_fast.py` - Primary MD5 scanner ⭐
- `scan_all_roots.py` - Multi-root orchestrator
- `find_filename_dupes.py` - Filename duplicates ⭐ NEW
- `scan_metadata.py` - Metadata extraction ⭐ NEW

**Duplicate Removal:**
- `prune_cross_root_duplicates.py` - Cross-root deduplication
- `prune_garbage_duplicates.py` - Rejected cleanup
- `dedupe_move_duplicates.py` - Move to Rejected
- `db_prune_missing_files.py` - DB reconciliation

**Health & Repair:**
- `flac_scan.py` - Deep health scanner
- `flac_repair.py` - FLAC repair
- `dedupe_repaired.py` - Repaired staging dedupe (consolidated)
- `reconcile_repaired.py` - Repaired vs MUSIC comparison

**Analysis:**
- `analyze_filename_dupes_metadata.py` - Metadata comparison ⭐ NEW
- `summarize_prune_csv.py` - CSV summarizer
- `verify_deleted_files.py` - Deletion audit

**Legacy Wrappers:**
- `dedupe_cli.py` → `dedupe.cli`
- `dedupe_sync.py` → `dedupe.sync`
- `analyze_quarantine_subdir.py` → `dedupe.legacy_cli` (legacy staging analysis)
- `simple_quarantine_scan.py` → `dedupe.legacy_cli` (legacy staging scan)
- `detect_playback_length_issues.py` → `dedupe.legacy_cli`

### 4. Documentation Updates

**Created:**
- `docs/scripts_reference.md` - Comprehensive script reference with:
  - Purpose and features for each script
  - Usage examples
  - Common workflow patterns
  - Database schema documentation
  - Quick reference guide

**Updated:**
- `README.md` - Added script organization section linking to detailed reference

### 5. Archive Script

Created `archive_scripts.sh` to automate the archiving process (run with `bash archive_scripts.sh`).

## Benefits

1. **Reduced Confusion**: Fewer scripts to choose from, clearer purposes
2. **Better Organization**: Scripts grouped by function
3. **Consolidated Features**: `dedupe_repaired.py` now handles both modes
4. **Complete Documentation**: Comprehensive reference in `docs/scripts_reference.md`
5. **Preserved History**: Archived scripts retained for reference

## Migration Notes

### For Users of Archived Scripts

**`dedupe_repaired_sizefirst.py` users:**
- Use `dedupe_repaired.py --fast` instead
- All functionality preserved with same arguments

**`find_dupes_fast_v2.py` users:**
- Use `find_dupes_fast.py` (SQLite-based, more robust)
- Better locking, resumability, and monitoring

**`find_exact_dupes.py` users:**
- Use `flac_scan.py` for comprehensive audio-MD5 scanning
- Or `find_dupes_fast.py` for fast file-MD5 (byte-identical)

## Recommended Next Steps

1. **Run archive script**: `bash archive_scripts.sh`
2. **Update workflows**: Replace archived script references
3. **Test consolidated tools**: Verify `dedupe_repaired.py --fast` works as expected
4. **Review docs**: Familiarize with new organization in `docs/scripts_reference.md`

## Database Schema Note

The metadata schema migration from individual columns to JSON storage is complete. The database now stores:
- **New JSON columns**: `vorbis_tags`, `audio_properties`, `format_info`
- **Legacy columns**: Retained for reference (artist, album, etc.)
- Use JSON columns for new queries and analysis
