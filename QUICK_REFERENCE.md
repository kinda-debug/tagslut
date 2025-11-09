# 🚀 Quick Reference Card

## See Progress RIGHT NOW

Open a **NEW terminal window** and use these commands:

### Quick Status
```bash
ps aux | grep find_dupes | grep -v grep
```
Shows: Is the fast scan running? What's the PID?

### Live Log (Best Option)
```bash
tail -f /tmp/scan_fast.log
```
Shows: Current file being hashed, progress update every file

### Current Results Count
```bash
wc -l /tmp/dupes_quarantine_fast.csv
```
Shows: How many duplicate groups found so far (updates as scan runs)

### Sample of What Was Found
```bash
head -10 /tmp/dupes_quarantine_fast.csv
```
Shows: Example of duplicate files found

### All at Once
```bash
echo "=== RUNNING ===" && ps aux | grep find_dupes | grep -v grep && echo -e "\n=== LOG ===" && tail -5 /tmp/scan_fast.log && echo -e "\n=== RESULTS ===" && wc -l /tmp/dupes_quarantine_fast.csv
```

## Launch Commands (If not started yet)

```bash
cd /Users/georgeskhawam/dedupe_repo

# Start FAST scan
bash launch.sh fast

# Start AUDIO scan (after or parallel)
bash launch.sh audio

# Start VALIDATION
bash launch.sh validate

# Check ALL status
bash launch.sh status

# STOP everything
bash launch.sh kill-all
```

## Expected Progress Indicators

### Just Started (First 1-2 min)
```
[INFO] Scanning /Volumes/dotad/Quarantine...
[INFO] Found 16700 audio files to hash
[1/16700] filename.flac...
[2/16700] filename.flac...
```

### Running Well (Mid-scan, 30+ min)
```
[500/16700] Hashing Some Band - Song Title.flac...
[1000/16700] Hashing Another Band - Track.flac...
```

### Nearly Done (90%+)
```
[15000/16700] filename.flac...
[16600/16700] filename.flac...
[16700/16700] Last file.flac...
[INFO] Found 1234 duplicate groups
```

## What's Running vs What's Not

### ✅ Scan IS Running If You See
```bash
$ ps aux | grep find_dupes
user  12345  0.0 0.5 200000 40000 ??  S   3:00PM  0:15 python3 scripts/find_dupes_fast.py
```

### ❌ Scan is NOT Running If You See
```bash
$ ps aux | grep find_dupes
# No output at all
```

## Files to Monitor

| File | What It Tells You |
|------|------------------|
| `/tmp/scan_fast.log` | Live progress of fast scan |
| `/tmp/dupes_quarantine_fast.csv` | Results as they're found |
| `/tmp/scan_audio.log` | Live progress of audio scan |
| `/tmp/dupes_quarantine_audio.csv` | Audio scan results |
| `~/.cache/file_dupes.db` | Fast scan database (grows) |
| `~/.cache/exact_dupes.db` | Audio scan database (if running) |

## Troubleshooting

### "I see nothing when I run the command"
- Scanner may not be running
- Try: `bash launch.sh status`
- Then: `bash launch.sh fast` to start it

### "Log file is huge and scrolling forever"
- Ctrl+C to stop following
- Check current position: `tail -c 500 /tmp/scan_fast.log` (last 500 bytes)

### "Results CSV has no data"
- Scan just started, give it time
- Fast scan needs at least 1 minute to hash first files
- Check log to see actual progress

### "I want to stop the scan"
```bash
bash launch.sh kill-all
```

## Expected Times

- **Fast Scan**: 30-60 min for 16,700 files
- **Audio Scan**: 10-20 hours for 16,700 files  
- **Validation**: Unknown (pending Batch 3)

## Files Created By Each Scan

### Fast Scan Creates
- `/tmp/scan_fast.log` - Progress log
- `/tmp/dupes_quarantine_fast.csv` - Results
- `~/.cache/file_dupes.db` - Database

### Audio Scan Creates
- `/tmp/scan_audio.log` - Progress log
- `/tmp/dupes_quarantine_audio.csv` - Results
- `~/.cache/exact_dupes.db` - Database

### Validation Creates
- `/tmp/validate_batch_3.log` - Progress log
- `/tmp/validate_Repaire_dupes.csv` - Results

## Most Important Command

### To see what's happening RIGHT NOW:
```bash
tail -f /tmp/scan_fast.log
```

That's it! Hit Ctrl+C to stop following when done.

---

**Having terminal issues?** Open a new terminal window (Terminal → New Window or Cmd+N). Processes continue in background.
