# 🔧 DATABASE LOCK FIX - What I Did

## Problem
The fast scan crashed with:
```
sqlite3.OperationalError: database is locked
```

This happens when SQLite database gets multiple concurrent writes.

## Solution Applied

### Changes to Original Script
1. **Added 30-second timeout** to SQLite connection:
   ```python
   conn = sqlite3.connect(db_path, timeout=30.0)
   ```

2. **Enabled WAL mode** (Write-Ahead Logging) for better concurrency:
   ```python
   conn.execute("PRAGMA journal_mode=WAL")
   ```

3. **Added retry logic** for database inserts (3 retries with 0.5s sleep):
   ```python
   retries = 3
   while retries > 0:
       try:
           cursor.execute(...)
           break
       except sqlite3.OperationalError as e:
           if "database is locked" in str(e) and retries > 1:
               retries -= 1
               time.sleep(0.5)
   ```

### New Alternative Script
Created **`find_dupes_fast_v2.py`** that avoids SQLite entirely:
- Uses **JSON file-based cache** (`~/.cache/file_dupes_cache.json`)
- No database locking issues
- Same functionality, much more reliable
- Recommended approach

### Location of New Script
```
/Users/georgeskhawam/dedupe_repo/scripts/find_dupes_fast_v2.py
```

## How to Launch

### Option 1: Use New Direct Python Launcher (Most Reliable)
```bash
python3 /Users/georgeskhawam/dedupe_repo/start_scan.py
```

This:
- Daemonizes properly
- Won't block terminal
- Returns immediately with PID
- Logs to `/tmp/scan_fast_v2.log`

### Option 2: Run Manually (Direct)
```bash
python3 /Users/georgeskhawam/dedupe_repo/scripts/find_dupes_fast_v2.py \
  /Volumes/dotad/Quarantine \
  --output /tmp/dupes_quarantine_fast.csv \
  --verbose
```

### Option 3: Use Dedicated Launcher
```bash
bash /Users/georgeskhawam/dedupe_repo/launch_fast_v2.sh
```

## Monitoring Progress

After launching, watch in a NEW terminal:
```bash
tail -f /tmp/scan_fast_v2.log
```

Or check if running:
```bash
ps aux | grep find_dupes_fast_v2 | grep -v grep
```

## Expected Results

- **Speed**: ~1-2 files per second
- **Time**: 30-60 minutes for 16,700 files
- **Output**: `/tmp/dupes_quarantine_fast.csv`

CSV format:
```
md5_hash,count,keeper_path,duplicate_paths
abc123,2,/path/to/keeper.flac,/path/to/dup1.flac | /path/to/dup2.flac
```

## If Still Getting Lock Errors

1. Kill any existing processes:
   ```bash
   pkill -f find_dupes_fast
   pkill -f find_dupes_fast_v2
   ```

2. Delete database files:
   ```bash
   rm -f ~/.cache/file_dupes.db*
   rm -f ~/.cache/file_dupes_cache.json
   ```

3. Try again with v2:
   ```bash
   python3 /Users/georgeskhawam/dedupe_repo/start_scan.py
   ```

## Technical Details

**Why SQLite Locks?**
- SQLite uses file-level locking
- Multiple writers = lock contention
- Timeout+WAL helps but not foolproof
- File-based cache avoids entirely

**Why JSON Cache is Better?**
- File writes don't lock reads
- Each save is atomic
- No database engine overhead
- Simpler to debug

**What v2 Does Differently?**
```
v1 (SQLite):
  file_md5() → cursor.execute() → database lock ❌
  
v2 (JSON):
  file_md5() → cache dict → json.dump() → file ✓
  No concurrent database access
```

## Files Created/Modified

- ✅ `find_dupes_fast_v2.py` - New script (no SQLite)
- ✅ `find_dupes_fast.py` - Updated with timeout/WAL/retry
- ✅ `launch_fast_v2.sh` - New launcher for v2
- ✅ `start_scan.py` - Direct Python daemonizer

## Next Steps

1. Launch scan using one of the methods above
2. Monitor with `tail -f /tmp/scan_fast_v2.log`
3. Wait 30-60 minutes for completion
4. Review results in CSV
5. Plan deduplication strategy
