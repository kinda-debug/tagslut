# Deduplication Scanning - Two Approaches

## Current Status: November 9, 2025 ~03:25 PM

Terminal display issues are preventing real-time monitoring, but scans are running in background.

## Two Scanning Scripts Created

### 1. **find_exact_dupes.py** (Audio-MD5 - High Accuracy)
- Hashes DECODED audio stream (what you actually hear)
- Finds audio-equivalent duplicates (different formats of same song)
- Slower: ~5-10 seconds per file
- More accurate but requires full audio decode
- **Status**: Had hang on file 51 (Genocide.flac)
- **Fixed**: Increased timeout to 120s, better error handling
- **Location**: `/Users/georgeskhawam/dedupe_repo/scripts/find_exact_dupes.py`

**Usage**:
```bash
python3 scripts/find_exact_dupes.py /Volumes/dotad/Quarantine \
    --output /tmp/dupes_quarantine.csv --verbose
```

### 2. **find_dupes_fast.py** (File-MD5 - High Speed) ⭐ RECOMMENDED
- Hashes FILE BYTES (structure, not decoded)
- Finds byte-identical file copies
- Fast: ~1-2 seconds per file
- 16,700 files = ~30-60 minutes
- **Better for**: Quick baseline deduplication
- **Location**: `/Users/georgeskhawam/dedupe_repo/scripts/find_dupes_fast.py`

**Usage**:
```bash
python3 scripts/find_dupes_fast.py /Volumes/dotad/Quarantine \
    --output /tmp/dupes_quarantine_fast.csv --verbose
```

## Key Differences

| Feature | find_exact_dupes | find_dupes_fast |
|---------|------------------|-----------------|
| Hash Type | AUDIO-MD5 (decoded) | FILE-MD5 (bytes) |
| Speed | 5-10 sec/file | 1-2 sec/file |
| Finds | Audio equivalents | Byte-identical |
| 16,700 files ETA | 20-50 hours | 1-2 hours |
| Accuracy | Very high | 100% byte match |
| Network FS | Issues possible | No issues |
| Corrupt files | May hang | Skip cleanly |

## Recommendation

**Use find_dupes_fast.py for immediate results:**

1. **Quick baseline** - Identify all exact file duplicates in Quarantine
2. **Safe deletion** - Delete byte-identical files (0 risk)
3. **Space savings** - Clean up immediately  
4. **Then assess** - After cleanup, can decide on audio-equiv scanning

## How to Run Both

### Fast scan (recommended first):
```bash
nohup python3 scripts/find_dupes_fast.py /Volumes/dotad/Quarantine \
    --output /tmp/dupes_quarantine_fast.csv --verbose \
    > /tmp/scan_fast.log 2>&1 &
```

### Audio scan (after cleanup, if needed):
```bash
nohup python3 scripts/find_exact_dupes.py /Volumes/dotad/Quarantine \
    --output /tmp/dupes_quarantine_audio.csv --verbose \
    > /tmp/scan_audio.log 2>&1 &
```

## Monitoring

**Quick status check**:
```bash
tail -5 /tmp/scan_fast.log
```

**Count progress**:
```bash
grep "^\[" /tmp/scan_fast.log | wc -l
```

**CSV results when complete**:
```bash
head -20 /tmp/dupes_quarantine_fast.csv
```

## Database Locations

- Fast scan DB: `~/.cache/file_dupes.db`
- Audio scan DB: `~/.cache/exact_dupes.db`

Both support:
- Resume from checkpoint
- Cross-directory reports
- Persistent storage

## Expected Output

CSV columns: `md5_hash,count,keeper_path,duplicate_paths`

Example:
```
abc123def456,3,/Volumes/dotad/Quarantine/song.flac,/Volumes/dotad/Quarantine/song-dup1.flac | /Volumes/dotad/Quarantine/song-dup2.flac
```

## Next Steps

1. ✅ Start fast scan: `find_dupes_fast.py`
2. Wait for completion (1-2 hours)
3. Review CSV results
4. Identify duplicates to delete
5. Move to `/Volumes/dotad/Garbage` (safe)
6. Then consider audio-equiv scan if needed

## Terminal Issues Workaround

If terminal is stuck:
```bash
# New terminal window
ps aux | grep "python3 scripts/find_dupes"

# Monitor without tail -f
while true; do echo "---$(date)---"; wc -l /tmp/scan_fast.log; sleep 5; done
```

Both scans will continue running even if terminal becomes unresponsive.
