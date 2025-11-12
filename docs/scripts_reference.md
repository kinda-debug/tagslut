# Script Organization and Reference

## Core Production Tools

### Duplicate Detection & Management

#### `find_dupes_fast.py` ⭐ PRIMARY
Fast file-MD5 byte-identical duplicate scanner.
- **Purpose**: Find exact file duplicates (byte-for-byte identical)
- **Database**: SQLite at `~/.cache/file_dupes.db`
- **Speed**: 1-2 sec/file (fast)
- **Usage**:
  ```bash
  python scripts/find_dupes_fast.py /Volumes/dotad/MUSIC \
    --output /tmp/dupes_music.csv \
    --heartbeat /tmp/heartbeat.txt \
    --watchdog --watchdog-timeout 180
  ```

#### `scan_all_roots.py`
Multi-root orchestrator for scanning MUSIC, Quarantine, and Garbage.
- **Purpose**: Scan all three roots sequentially into shared DB
- **Usage**:
  ```bash
  python scripts/scan_all_roots.py \
    --db ~/.cache/file_dupes.db \
    --output artifacts/reports/dupes_all.csv
  ```

#### `find_filename_dupes.py` ⭐ NEW
Find files with identical names (filename-based duplicates).
- **Purpose**: Match Dupeguru's filename mode
- **Finds**: Same basename, different content (metadata differences)
- **Usage**:
  ```bash
  python scripts/find_filename_dupes.py \
    --report artifacts/reports/filename_dupes.csv
  ```

### Duplicate Removal

#### `dedupe_move_duplicates.py`
Move byte-identical duplicates to Garbage.
- **Safety**: Dry-run by default (`--commit` to execute)
- **Keeper Selection**: Shortest path → lexicographic
- **Usage**:
  ```bash
  # Plan
  python scripts/dedupe_move_duplicates.py \
    --report artifacts/reports/planned_moves.csv

  # Execute
  python scripts/dedupe_move_duplicates.py --commit \
    --report artifacts/reports/executed_moves.csv
  ```

#### `prune_cross_root_duplicates.py` ⭐ CRITICAL
Delete duplicates across all roots (MUSIC, Quarantine, Garbage).
- **Policy**: Pure shortest-path (NO root preference)
- **Safety**: Dry-run by default (`--commit` to execute)
- **CSV Columns**:
  - Dry-run: `md5, path, size_bytes, reason, keeper`
  - Executed: adds `status, error` columns
- **Usage**:
  ```bash
  # Plan
  python scripts/prune_cross_root_duplicates.py \
    --db ~/.cache/file_dupes.db \
    --report artifacts/reports/cross_root_prune_plan.csv

  # Execute
  python scripts/prune_cross_root_duplicates.py --commit \
    --db ~/.cache/file_dupes.db \
    --report artifacts/reports/cross_root_prune_executed.csv
  ```

#### `prune_garbage_duplicates.py`
Safe Garbage-only cleanup.
- **Rules**:
  1. If duplicate exists outside Garbage → delete all Garbage copies
  2. If only in Garbage → keep shortest path, delete rest
- **Usage**:
  ```bash
  python scripts/prune_garbage_duplicates.py \
    --db ~/.cache/file_dupes.db \
    --report artifacts/reports/garbage_prune_plan.csv
  ```

### Database Maintenance

#### `db_prune_missing_files.py`
Remove stale DB entries for deleted files.
- **Scope**: Garbage by default, `--scope all` for complete cleanup
- **Usage**:
  ```bash
  python scripts/db_prune_missing_files.py \
    --db ~/.cache/file_dupes.db \
    --report artifacts/reports/db_cleanup.csv
  ```

### Metadata Management

#### `scan_metadata.py` ⭐ NEW
Extract and store comprehensive FLAC metadata.
- **Storage**: JSON columns (vorbis_tags, audio_properties, format_info)
- **Tools**: metaflac (Vorbis tags), ffprobe (audio properties)
- **Usage**:
  ```bash
  # Scan single root
  python scripts/scan_metadata.py /Volumes/dotad/MUSIC

  # Scan all roots
  python scripts/scan_metadata.py --all-roots

  # Limit for testing
  python scripts/scan_metadata.py --all-roots --limit 100
  ```

#### `analyze_filename_dupes_metadata.py`
Compare metadata for filename duplicates.
- **Purpose**: Decide keeper based on metadata quality
- **Criteria**: Tag completeness, artwork, audio quality
- **Usage**:
  ```bash
  python scripts/analyze_filename_dupes_metadata.py \
    --report artifacts/reports/filename_dupes_analysis.csv
  ```

### Health & Repair

#### `flac_scan.py`
Deep health scanner with audio fingerprinting.
- **Features**: 
  - FLAC test (`flac -t`)
  - Audio MD5 (decoded content)
  - Chromaprint fingerprinting
  - Freeze detection
- **Usage**:
  ```bash
  python scripts/flac_scan.py --root /Volumes/dotad/MUSIC \
    --workers 8 --verbose
  ```

#### `flac_repair.py`
Repair FLAC files using ffmpeg.
- **Input**: M3U playlist or single file
- **Safety**: Creates repaired copies, preserves originals
- **Usage**:
  ```bash
  python scripts/flac_repair.py --playlist broken.m3u \
    --output /path/to/repaired
  ```

### Specialized Tools

#### `dedupe_repaired.py`
Find content duplicates in repaired staging directory.
- **Methods**:
  - Normal: Scan all files (comprehensive)
  - `--fast`: Size-first optimization (faster)
- **Hash**: PCM SHA1 (audio content, not file bytes)
- **Usage**:
  ```bash
  # Normal mode
  python scripts/dedupe_repaired.py \
    --repaired /path/to/ReallyRepaired \
    --out repaired_dupes.csv

  # Fast mode (recommended for large trees)
  python scripts/dedupe_repaired.py --fast \
    --repaired /path/to/ReallyRepaired \
    --out repaired_dupes.csv \
    --move --quarantine /path/to/quarantine
  ```

#### `reconcile_repaired.py`
Compare repaired staging against MUSIC library.
- **Recommendations**: Keep, replace, skip
- **Usage**:
  ```bash
  python scripts/reconcile_repaired.py \
    --repaired /Volumes/dotad/ReallyRepaired \
    --music /Volumes/dotad/MUSIC \
    --out report.csv
  ```

### Utility Scripts

#### `summarize_prune_csv.py`
Aggregate prune plan/executed CSV statistics.
- **Output**: Counts, sizes by (reason, status)
- **Usage**:
  ```bash
  python scripts/summarize_prune_csv.py \
    artifacts/reports/garbage_prune_executed.csv
  ```

#### `verify_deleted_files.py`
Audit deleted files and verify keepers.
- **Checks**: Keeper exists, size match, policy compliance
- **Usage**:
  ```bash
  python scripts/verify_deleted_files.py
  ```

## Archived Scripts

See `archive/scripts_diagnostic_2025/` for:
- One-time migration scripts (`migrate_metadata_schema.py`)
- Diagnostic tools (`check_schema.py`, `verify_json_metadata.py`)
- Experimental versions (`find_dupes_fast_v2.py`, `find_exact_dupes.py`)
- Superseded implementations (`dedupe_repaired_sizefirst.py`)

## Legacy Wrappers

These delegate to the `dedupe` package:
- `scripts/dedupe_cli.py` → `dedupe.cli`
- `scripts/dedupe_sync.py` → `dedupe.sync`
- `scripts/analyze_quarantine_subdir.py` → `dedupe.legacy_cli`
- `scripts/simple_quarantine_scan.py` → `dedupe.legacy_cli`
- `scripts/detect_playback_length_issues.py` → `dedupe.legacy_cli`

## Quick Reference: Common Workflows

### 1. Initial Scan (All Roots)
```bash
python scripts/scan_all_roots.py \
  --db ~/.cache/file_dupes.db \
  --output artifacts/reports/dupes_all.csv
```

### 2. Cross-Root Deduplication
```bash
# Plan
python scripts/prune_cross_root_duplicates.py \
  --report artifacts/reports/plan.csv

# Review plan.csv, then execute
python scripts/prune_cross_root_duplicates.py --commit \
  --report artifacts/reports/executed.csv

# Clean DB
python scripts/db_prune_missing_files.py \
  --report artifacts/reports/db_cleanup.csv
```

### 3. Filename Duplicate Analysis
```bash
# Find filename duplicates
python scripts/find_filename_dupes.py \
  --report artifacts/reports/filename_dupes.csv

# Scan metadata
python scripts/scan_metadata.py --all-roots

# Analyze metadata quality
python scripts/analyze_filename_dupes_metadata.py \
  --report artifacts/reports/metadata_comparison.csv
```

### 4. Garbage Cleanup
```bash
python scripts/prune_garbage_duplicates.py --commit \
  --report artifacts/reports/garbage_cleanup.csv
```

## Database Schema

### `file_hashes` table

**Core columns:**
- `file_path` (TEXT PRIMARY KEY)
- `file_md5` (TEXT) - File MD5 hash
- `file_size` (INTEGER) - Bytes
- `scan_time` (TEXT) - ISO timestamp

**Metadata columns (JSON):**
- `vorbis_tags` (TEXT) - All Vorbis comments as JSON
- `audio_properties` (TEXT) - ffprobe stream data as JSON
- `format_info` (TEXT) - ffprobe format data as JSON
- `has_artwork` (INTEGER) - 0/1 boolean
- `artwork_count` (INTEGER) - Number of embedded pictures
- `metadata_scanned` (INTEGER) - 0/1 flag

**Legacy columns (deprecated, retained for reference):**
- `artist`, `album`, `title`, `date`, `genre`, etc.
- Use JSON columns for new queries

## Environment Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Testing

```bash
export PYTHONPATH="$(pwd)"
pytest -q
```
