# Scripts Directory

Operational scripts for music library management. Organized by function and execution context.

## Active Scripts

### Root Level - Primary Workflows

- **`scan_not_scanned.py`** - Resumable scanner for NOT_SCANNED files (database-driven, interrupt-safe)
- **`quarantine_small_dupes.py`** - Quarantine small/short duplicates (<10MB, <90s) for AcoustID verification
- **`recover_workflow.py`** - File recovery workflow automation
- **`validate_config.py`** - Configuration file validation
- **`safe_to_delete_presence.py`** - Safe deletion presence checker
- **`backup_dbs.sh`** - Database backup utility

### Python Utilities (`python/`)

#### Metadata Management
- **`rebuild_metadata.py`** - Rebuild metadata for healthy FLACs (copies to structured directories)
- **`fix_empty_metadata.py`** - Fix files with missing/empty metadata fields
- **`update_extra_json.py`** - Update extra_json fields in database

#### Duplicate Detection & Ranking
- **`rank_duplicates.py`** - Rank duplicates in library_final.db by quality/preference

#### Library Operations
- **`reorg_canonical_library.py`** - Reorganize canonical library structure
- **`rescan_and_merge.py`** - Rescan directories and merge into canonical DB
- **`scan_final_library.py`** - Scan final library state

#### Qobuz Playlist Management
- **`qobuz_playlist_dedupe.py`** - **ONLINE** Qobuz playlist deduper (requires API credentials)
  - Authenticates with Qobuz API (app_id + email/password)
  - Fetches all user playlists and tracks
  - Deduplicates using ISRC → normalized (artist,title) → track_id
  - Outputs: JSON + CSV per playlist, summary CSV
  
- **`offline_qobuz_playlist_dedupe.py`** - **OFFLINE** Qobuz playlist deduper (works on exports)
  - No API calls - processes local CSV/JSON exports
  - Accepts CSV (playlist_name, track_id, artist, title, isrc, etc.) or JSON payloads
  - Same deduplication logic as online version
  - Use when: Already have exports, API unavailable, or batch processing local data

#### Volume/FLAC Analysis
- **`group_bad_flacs.py`** - Group bad FLAC files for analysis

### Shell Scripts (`shell/`)

#### Library Building
- **`build_final_library.sh`** - Build final library DB from scan DBs
- **`scan_all_sources_and_build_final.sh`** - Comprehensive scan of all source roots + merge to final DB
- **`finalize_library.sh`** - Final library preparation steps
- **`scan_final_library.sh`** - Final library scanning

#### Deduplication & Cleanup
- **`dedupe_commune_move_dupes.sh`** - Move non-canonical FLAC duplicates to 90_REJECTED
- **`apply_dedupe_plan.sh`** - Apply deduplication plan from decision output
- **`clean_empty_dirs_commune.sh`** - Clean empty directories on COMMUNE volume

#### Recovery & Reporting
- **`recovery_only_pipeline.sh`** - Recovery-focused processing pipeline
- **`report_canonical_summary.sh`** - Generate canonical library summary report
- **`verify_commune_dedup_state.sh`** - Verify deduplication state on COMMUNE

#### Utilities
- **`setup.sh`** - Project setup script
- **`archive_scripts_cleanup.sh`** - Archive/cleanup old scripts

### JXA Scripts (`jxa/`)

JavaScript for Automation scripts for macOS integration.

## Archive (`archive/`)

Deprecated or one-time-use scripts are kept in the repository history. Use this directory
to place any scripts you explicitly want archived for future reference.

- **Placeholder:** `scripts/archive/.gitkeep`

## Usage Patterns

### Scanning NOT_SCANNED Files
```bash
# Resumable, database-driven, interrupt-safe
python3 scripts/scan_not_scanned.py <library> <zone> <batch_size>

# Example: Scan bad/suspect volume in 5000-file batches
python3 scripts/scan_not_scanned.py bad suspect 5000
```

### Qobuz Playlist Deduplication
```bash
# Online (requires credentials in config)
python3 scripts/python/qobuz_playlist_dedupe.py --email user@example.com

# Offline (from exports)
python3 scripts/python/offline_qobuz_playlist_dedupe.py --csv playlists.csv --json-dir exports/
```

### Full Library Rebuild
```bash
# Scan all sources and merge to final library
./scripts/shell/scan_all_sources_and_build_final.sh
```

### Duplicate Cleanup
```bash
# Move duplicates to rejection directory
./scripts/shell/dedupe_commune_move_dupes.sh
```

## Design Principles

1. **Resumability** - Scripts handle interrupts gracefully, use database as checkpoint
2. **Idempotency** - Safe to run multiple times without corruption
3. **Logging** - All operations log to `artifacts/logs/`
4. **Validation** - Check preconditions, fail fast with clear errors
5. **Documentation** - Headers explain purpose, usage, and dependencies

## Adding New Scripts

- Place in appropriate subdirectory (`python/` or `shell/`)
- Add comprehensive docstring/header comment
- Update this README with description and usage
- Consider archiving if replacing existing functionality
