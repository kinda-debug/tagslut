# 🚀 Proper Background Job Launching System

## ✅ Problem Solved
No more running huge long-running processes directly in terminal!

## 📁 Launcher Scripts

All scripts are in the repo root and handle:
- ✅ Proper background execution with nohup
- ✅ Output redirection to log files
- ✅ Clean process management
- ✅ Status checking
- ✅ Easy monitoring

## 🎯 How to Use

### Main Launcher (Universal)
```bash
cd /Users/georgeskhawam/dedupe_repo

# Show help
bash launch.sh

# Start fast scan
bash launch.sh fast

# Start audio scan
bash launch.sh audio

# Start validation
bash launch.sh validate

# Check status
bash launch.sh status

# Kill all running scans
bash launch.sh kill-all
```

### Individual Launchers (if preferred)
```bash
# Fast file-MD5 scan
bash launch_fast_scan.sh

# Audio-MD5 scan
bash launch_audio_scan.sh

# Batch 3 validation
bash launch_validation_batch3.sh
```

## 📊 Current Status

**Check what's running:**
```bash
bash launch.sh status
```

**Monitor any running process:**
```bash
tail -f /tmp/scan_fast.log           # Fast scan progress
tail -f /tmp/scan_audio.log          # Audio scan progress
tail -f /tmp/validate_batch_3.log    # Validation progress
```

**View results when complete:**
```bash
head -20 /tmp/dupes_quarantine_fast.csv
head -20 /tmp/dupes_quarantine_audio.csv
head -20 /tmp/validate_Repaire_dupes.csv
```

## 🔄 Workflow

### Step 1: Start Fast Scan (Recommended First)
```bash
bash launch.sh fast
# Output: Process started with PID: 12345
# Monitor: tail -f /tmp/scan_fast.log
```

### Step 2: Wait for Completion
- Fast scan: 30-60 minutes (16,700 files)
- Check progress: `tail -f /tmp/scan_fast.log`
- Check PID: `ps -p 12345`

### Step 3: Review Results
```bash
# How many duplicates found?
wc -l /tmp/dupes_quarantine_fast.csv

# See duplicate groups
head -20 /tmp/dupes_quarantine_fast.csv

# See largest duplicate groups
sort -t, -k2 -rn /tmp/dupes_quarantine_fast.csv | head -20
```

### Step 4: Plan Deduplication
- Review CSV
- Identify which duplicates to delete
- Move to `/Volumes/dotad/Garbage` (safe)

### Step 5: Optional - Audio Scan (If Needed)
```bash
bash launch.sh audio
# Wait 10-20 hours for completion
```

### Step 6: Batch 3 Validation
```bash
bash launch.sh validate
# Will validate Repaire_dupes directory
```

## 📋 CSV Output Format

Each scan produces CSV with:
```
hash,count,keeper_path,duplicate_paths
```

Example row:
```
abc123def456,3,/Volumes/dotad/Quarantine/song.flac,/Volumes/dotad/Quarantine/song-dup1.flac | /Volumes/dotad/Quarantine/song-dup2.flac
```

Columns:
- **hash**: File MD5 (fast) or Audio MD5 (accurate)
- **count**: Number of identical copies
- **keeper_path**: Which file to keep
- **duplicate_paths**: Files to delete (pipe-separated)

## 🎯 Key Benefits

✅ **Background processes don't block terminal**
✅ **Logs saved to files for review**
✅ **Easy to check status later**
✅ **Can close terminal, processes continue**
✅ **Proper cleanup with kill command**
✅ **All outputs organized**

## 📍 Output Locations

### Logs
- `/tmp/scan_fast.log` - Fast scan progress
- `/tmp/scan_audio.log` - Audio scan progress
- `/tmp/validate_batch_3.log` - Validation progress

### Results CSV
- `/tmp/dupes_quarantine_fast.csv` - Fast scan results
- `/tmp/dupes_quarantine_audio.csv` - Audio scan results
- `/tmp/validate_Repaire_dupes.csv` - Validation results

### Databases
- `~/.cache/file_dupes.db` - Fast scan data
- `~/.cache/exact_dupes.db` - Audio scan data

## 🛠️ Advanced Usage

### Monitor multiple processes
```bash
# Terminal 1: Monitor fast scan
tail -f /tmp/scan_fast.log

# Terminal 2: Run audio scan while fast scan is running
bash launch.sh audio

# Terminal 3: Run validation
bash launch.sh validate
```

### Kill specific process
```bash
pkill -f "find_dupes_fast"
pkill -f "find_exact_dupes"
pkill -f "validate_repair"
```

### Resume interrupted scan
```bash
# Same command will resume from checkpoint
bash launch.sh fast
```

## ⚡ Quick Start

```bash
cd /Users/georgeskhawam/dedupe_repo

# 1. Start fast scan
bash launch.sh fast

# 2. Monitor in separate terminal
tail -f /tmp/scan_fast.log

# 3. When done, check results
wc -l /tmp/dupes_quarantine_fast.csv
head -20 /tmp/dupes_quarantine_fast.csv
```

That's it! All processes run cleanly in the background.
