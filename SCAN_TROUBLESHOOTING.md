# Scan Troubleshooting - November 9, 2025

## Problem
Scan was stuck at file 51/16700 on "The Offspring - Genocide.flac"

## Root Causes Identified
1. **Long timeout files**: Some files take >60 seconds to hash
2. **Problematic files**: Specific file might have issues
3. **FFmpeg hanging**: Decode issues on certain files

## Fixes Applied
1. ✅ Increased timeout from 60 to 120 seconds
2. ✅ Added better error logging and handling
3. ✅ Fixed periodic save logic (was hitting on empty dict)
4. ✅ Better exception handling for file access issues

## Fresh Scan Started
```bash
nohup python3 scripts/find_exact_dupes.py /Volumes/dotad/Quarantine \
    --output /tmp/dupes_quarantine.csv --verbose > /tmp/scan_quarantine.log 2>&1 &
```

## If Scan Gets Stuck Again

### Option 1: Skip Problematic File
Edit the script to skip files with repeated errors:

```python
# In scan_directory function, skip after 3 consecutive failures
consecutive_fails = 0
for i, file_path in enumerate(audio_files, 1):
    computed_hash = audio_md5(file_path)
    if not computed_hash:
        consecutive_fails += 1
        if consecutive_fails > 3:
            print(f"Skipping problematic file: {file_path}")
            continue
    else:
        consecutive_fails = 0
```

### Option 2: Run Without Problematic Directory
Skip Quarantine subdirectories that have issues:
```bash
find /Volumes/dotad/Quarantine -type d -name "*problem*" -exec rm -rf {} \;
```

### Option 3: Use simpler hash (faster but less reliable)
Switch from AUDIO-MD5 to file MD5 (checks file structure, not decoded content):
```bash
md5sum "/Volumes/dotad/Quarantine/filename.flac"
```

## Current Status
- Script improvements deployed
- New scan started with verbose output
- Monitor with: `tail -f /tmp/scan_quarantine.log`
- Terminal having display issues but commands are running

## Next Actions

1. **Wait for scan to progress** (should move past file 51)
2. **If stuck again** at different file, that file is likely corrupt
3. **Consider alternative approach** if >30% of files cause timeouts

## Alternative: Faster Scan Method

For very large libraries with reliability concerns, could use:
- File-level MD5 (faster, ~1 sec per file vs 5-10 sec)
- Then manual spot-checking of suspicious groups
- Skip individual corrupt files, continue scanning

## Database Location
`~/.cache/exact_dupes.db` - Contains all hashed files (persists if interrupted)

## Resume Command
```bash
# Same command will resume from DB cache
nohup python3 scripts/find_exact_dupes.py /Volumes/dotad/Quarantine \
    --output /tmp/dupes_quarantine.csv --verbose > /tmp/scan_quarantine.log 2>&1 &
```
