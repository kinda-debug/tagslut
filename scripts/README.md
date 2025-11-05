# Scripts Directory

Consolidated Python and shell scripts for FLAC deduplication workflow.

## Organization

**Total Scripts: 13** (down from 27, -52% reduction)

### Core Algorithm Modules (4 files)
Core audio processing and deduplication logic:

- **`flac_scan.py`** - Scan music library, compute hashes & fingerprints, build database index
- **`flac_dedupe.py`** - Identify duplicate FLAC files by hash and fingerprint
- **`flac_repair.py`** - Repair corrupted/broken FLAC files using ffmpeg
- **`dedupe_sync.py`** - Synchronize and move files between staging and library with health checks

### Unified Manager Scripts (4 files)
Single entry points for related operations:

- **`dedupe_cli.py`** - Master CLI router for all commands (scan, repair, dedupe, workflow, status, clean)
- **`dedupe_plan_manager.py`** - CSV-based dedupe operations (check, apply, verify)
- **`repair_workflow.py`** - Repair candidate workflow (search, combine, mark-irretrievable, run)
- **`post_repair.py`** - Post-repair utilities (clean-playlist, promote)

### Consolidated Utilities (1 file)
Filesystem and operational utilities:

- **`file_operations.py`** - File operations manager (archive, move-trash, collect-logs)
  - Consolidated from: `archive_root.sh`, `move_dupes_to_trash.sh`, `collect_repair_logs.sh`

### Specialized Scripts (2 files)
Specialized tools with complex logic:

- **`stage_hash_dupes.sh`** - Stage hash-based duplicates (complex SQL+bash, kept as-is)
- **`run_remaining_repairs.sh`** - Run repair batch from list (thin orchestration wrapper)

## Usage Examples

### Via Root-Level CLI (Recommended)
Use the unified `./dedupe` CLI from repository root:

```bash
# Core workflow
./dedupe scan --root /path/to/music
./dedupe repair --file broken.flac
./dedupe dedupe --dry-run
./dedupe workflow --commit

# Plan management
./dedupe plan check --csv report.csv
./dedupe plan apply --dry-run
./dedupe plan verify

# Repair workflow
./dedupe repair-workflow search --basenames missing.txt
./dedupe repair-workflow run

# Post-repair
./dedupe post-repair clean-playlist
./dedupe post-repair promote --src /path/to/repaired

# File operations
./dedupe file-ops archive --root .
./dedupe file-ops move-trash --dry-run
./dedupe file-ops collect-logs
```

### Direct Script Invocation
Call manager scripts directly with subcommands:

```bash
python scripts/dedupe_cli.py scan --verbose
python scripts/dedupe_plan_manager.py check --csv report.csv
python scripts/repair_workflow.py search --basenames candidates.txt
python scripts/post_repair.py clean-playlist
python scripts/file_operations.py archive --root .
```

### Specialized Commands
```bash
bash scripts/stage_hash_dupes.sh "$db" "$music_root" 25 false
bash scripts/run_remaining_repairs.sh
```

## Consolidation Summary

### Phase 1: ✅ Complete
Deleted 10 obsolete wrapper scripts already replaced by managers:
- check_dedupe_plan.py, apply_dedupe_plan.py, verify_post_move.py
- find_missing_candidates.py, combine_found_candidates.py, mark_irretrievable.py, repair_unhealthy.py
- remove_repaired.py, promote_and_patch.py, dd_flac_dedupe_db.py

### Phase 2: ✅ Complete
Merged flac_workflow.py into dedupe_cli.py as "workflow" subcommand

### Phase 3: ✅ Complete
Consolidated shell utilities into file_operations.py:
- archive_root.sh → file_operations.py archive
- move_dupes_to_trash.sh → file_operations.py move-trash
- collect_repair_logs.sh → file_operations.py collect-logs

## Quality Metrics

✅ **No monolithic files** - Largest module <3,000 LOC  
✅ **Independent testability** - Each module can be tested separately  
✅ **Backward compatible** - All existing commands still work  
✅ **52% reduction** - Down to 13 scripts from 27 original  
✅ **Cross-platform** - Python consolidation improves portability
