# find_exact_dupes.py - Database-Backed Duplicate Scanner

## Overview

The script has been completely rewritten to use **SQLite database persistence** instead of losing all data at each run. It can now be used to:

1. **Scan multiple directories** (MUSIC, Quarantine, etc.) and store all hashes in persistent DB
2. **Generate cross-library reports** showing duplicates across entire library
3. **Resume from interruption** (Ctrl+C)
4. **Track scanning history** with session metadata

## Database Schema

### Tables

**file_hashes:**
```sql
CREATE TABLE file_hashes (
    file_path TEXT PRIMARY KEY,
    audio_hash TEXT NOT NULL,
    file_size INTEGER,
    scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
- Indexed on `audio_hash` for fast lookups

**scan_sessions:**
```sql
CREATE TABLE scan_sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    directory TEXT,
    file_count INTEGER,
    scanned_count INTEGER,
    scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```
- Tracks metadata about each scan session

## Usage

### Scan a single directory
```bash
python3 scripts/find_exact_dupes.py /Volumes/dotad/Quarantine \
    --output /tmp/dupes_quarantine.csv
```

### Scan another directory (adds to same DB)
```bash
python3 scripts/find_exact_dupes.py /Volumes/dotad/MUSIC \
    --output /tmp/dupes_music.csv
```

### Generate cross-library deduplication report
```bash
python3 scripts/find_exact_dupes.py --report \
    --output /tmp/cross_dupes.csv
```

### Custom database location
```bash
python3 scripts/find_exact_dupes.py /Volumes/dotad/Quarantine \
    --db /custom/path/dupes.db \
    --output /tmp/dupes.csv
```

## Database Locations

- **Default:** `~/.cache/exact_dupes.db` (SQLite - persistent)
- **Temp cache:** `~/.cache/exact_dupes_current.json` (JSON - for resume within a scan)

## Features

✅ **Persistent Storage**: All hashes stored in SQLite, survives interruptions
✅ **Resumable**: Temp JSON cache allows resume within a scan session
✅ **Interruptible**: Ctrl+C saves progress gracefully
✅ **Cross-Library**: Scan multiple directories, find dupes across entire library
✅ **Session Tracking**: Records metadata about each scan
✅ **Fast Lookups**: Indexed by audio hash for quick duplicate detection
✅ **CSV Reports**: Generates reports for each scan + cross-library reports

## Output Format

CSV files contain:
```
hash,count,keeper_path,duplicate_paths
abc123def456...,3,/path/to/keep.flac,/path/to/delete1.flac | /path/to/delete2.flac
```

- `hash`: The AUDIO-MD5 hash of the decoded stream
- `count`: Number of identical files found
- `keeper_path`: Which file to keep (first occurrence)
- `duplicate_paths`: Files that can be deleted (pipe-separated)

## Workflow Example

```bash
# Scan Quarantine directory (~16,700 files, resumable with Ctrl+C)
python3 scripts/find_exact_dupes.py /Volumes/dotad/Quarantine \
    --output /tmp/dupes_quarantine.csv \
    --verbose

# Scan MUSIC library
python3 scripts/find_exact_dupes.py /Volumes/dotad/MUSIC \
    --output /tmp/dupes_music.csv

# Scan repairedforreal
python3 scripts/find_exact_dupes.py /Volumes/dotad/repairedforreal \
    --output /tmp/dupes_repaired.csv

# Generate cross-library report (all duplicates across all directories)
python3 scripts/find_exact_dupes.py --report \
    --output /tmp/cross_dupes.csv

# Now you have:
# - dupes_quarantine.csv (dupes within Quarantine)
# - dupes_music.csv (dupes within MUSIC)
# - dupes_repaired.csv (dupes within repairedforreal)
# - cross_dupes.csv (dupes found across ALL directories)
```

## Implementation Details

- **JSON Cache**: Temporary cache during scan for fast resume if interrupted
- **SQLite DB**: Permanent storage of all scanned files and their hashes
- **Signal Handler**: Catches Ctrl+C and sets global `interrupted` flag
- **Graceful Shutdown**: On interrupt, saves temp cache and current DB state
- **File Size Tracking**: Records file size for additional verification
- **Timestamp Tracking**: Records when each file was hashed

## Next Steps

1. Scan Quarantine directory (largest collection, 16,700+ files)
2. Scan MUSIC library
3. Generate cross-library deduplication report
4. Use report to identify and safely delete duplicates
5. Then focus on re-repairing invalid/truncated files from earlier batches
