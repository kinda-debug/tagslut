# Exact Duplicates Scan - Ready to Execute

## Status: ✅ READY

The `find_exact_dupes.py` script has been completely rewritten with database persistence. 

## What Changed

### Before (Lost Data)
- JSON-only cache
- Data lost on each run
- No cross-library tracking

### After (Database Persistent) 
- SQLite DB: `~/.cache/exact_dupes.db`
- Permanent storage of all hashes
- Cross-library deduplication capability
- JSON temp cache for resumability within scan

## Database Schema

```sql
-- Stores all scanned files with their audio hashes
CREATE TABLE file_hashes (
    file_path TEXT PRIMARY KEY,
    audio_hash TEXT NOT NULL,
    file_size INTEGER,
    scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)

-- Tracks scanning sessions
CREATE TABLE scan_sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    directory TEXT,
    file_count INTEGER,
    scanned_count INTEGER,
    scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

## Next Commands to Run

### 1. Scan Quarantine (16,700+ files, ~2-3 hours)
```bash
cd /Users/georgeskhawam/dedupe_repo
nohup python3 scripts/find_exact_dupes.py /Volumes/dotad/Quarantine \
    --output /tmp/dupes_quarantine.csv > /tmp/scan_quarantine.log 2>&1 &

# Monitor progress
tail -f /tmp/scan_quarantine.log
```

### 2. Scan MUSIC library
```bash
nohup python3 scripts/find_exact_dupes.py /Volumes/dotad/MUSIC \
    --output /tmp/dupes_music.csv > /tmp/scan_music.log 2>&1 &
```

### 3. Scan repairedforreal (50 validated files)
```bash
nohup python3 scripts/find_exact_dupes.py /Volumes/dotad/repairedforreal \
    --output /tmp/dupes_repaired.csv > /tmp/scan_repaired.log 2>&1 &
```

### 4. Generate cross-library deduplication report
```bash
python3 scripts/find_exact_dupes.py --report \
    --output /tmp/cross_dupes.csv
```

## Output Files

After scanning, you'll have:

- `/tmp/dupes_quarantine.csv` - Duplicates within Quarantine only
- `/tmp/dupes_music.csv` - Duplicates within MUSIC only  
- `/tmp/dupes_repaired.csv` - Duplicates within repairedforreal
- `/tmp/cross_dupes.csv` - Duplicates found across ALL directories
- `~/.cache/exact_dupes.db` - SQLite database with all hash data

## CSV Format

Each CSV has columns:
```
hash,count,keeper_path,duplicate_paths
```

Example row:
```
abc123def456...,3,/Volumes/dotad/Quarantine/song1.flac,/Volumes/dotad/Quarantine/song1-copy.flac | /Volumes/dotad/Quarantine/song1-dup.flac
```

## Features

✅ **Resumable**: Ctrl+C + re-run same command continues from checkpoint
✅ **Interruptible**: Can stop with Ctrl+C, DB is saved
✅ **Cross-Library**: Combine data from multiple directories in one DB
✅ **Fast Lookups**: Indexed on audio hash
✅ **Session Tracking**: See when each directory was scanned

## Expected Results

Based on your library size:
- Quarantine (~16,700 files): Likely ~1,000-2,000 duplicate groups
- MUSIC (~50,000 files estimated): Likely ~2,000-5,000 duplicate groups
- Cross-library: Identify Quarantine dupes that exist in MUSIC

## Next Phase After Scanning

Once you have the cross-library CSV report:

1. Review deletion candidates (duplicate_paths column)
2. Move duplicates to `/Volumes/dotad/Garbage` (safe)
3. Or delete if confident
4. Then address the 7 invalid/truncated files from validation:
   - 4 truncated in ReallyRepaired
   - 3 invalid in REPAIRED_FLACS

## Implementation Notes

- FFmpeg MD5 hashing: Decodes full audio stream for exact comparison
- Database queries: Efficient deduplication across directories
- Signal handling: Graceful Ctrl+C with checkpoint save
- File size tracking: Additional verification layer
- Timestamp tracking: Know when each file was analyzed
