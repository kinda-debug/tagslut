# Troubleshooting Guide

Common issues and their solutions.

## Authentication Issues

### Problem: Tidal Token Expired

**Symptoms:**
- `extract_tracklists_from_links.py` returns `tidal_token_missing`
- Tidal links not extracted

**Solution:**
```bash
# Check token status
tagslut auth status

# Refresh token
tagslut auth refresh

# If refresh fails, re-authenticate
tagslut auth login
```

### Problem: Beatport API Issues

**Symptoms:**
- `http_403` or `http_429` errors
- `next_data_not_found` errors

**Solution:**
Beatport uses web scraping with fallback to API. If scraping fails:
1. Wait and retry (rate limiting)
2. Check if Beatport site structure changed
3. Use individual track URLs instead of large releases

---

## Database Issues

### Problem: Database Locked

**Symptoms:**
- `sqlite3.OperationalError: database is locked`

**Solution:**
```bash
# Find processes using the database
lsof +D ~/Projects/tagslut_db/

# Kill any stale processes
# Then retry operation
```

### Problem: Database Not Found

**Symptoms:**
- `DB not found: /path/to/music.db`

**Solution:**
```bash
# Check the path exists
ls -la ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# Check .env configuration
cat .env | grep TAGSLUT_DB
```

---

## Pre-Download Check Issues

### Problem: Extract Script Not Found

**Symptoms:**
- `Extract script not found: /path/to/extract_tracklists_from_links.py`

**Solution:**
```bash
# Run from repo root
cd ~/Projects/tagslut
source .venv/bin/activate

# The script is at:
ls scripts/extract_tracklists_from_links.py
```

### Problem: No Tracks Extracted

**Symptoms:**
- Output shows `tracks_total: 0`
- Links show `status: error`

**Solution:**
1. Check if URLs are valid and accessible
2. Check if token is valid for Tidal links
3. Try individual track URLs instead of playlists/releases

---

## Move Execution Issues

### Problem: Move Failed - Permission Denied

**Symptoms:**
- `PermissionError` during move
- Files not moved

**Solution:**
```bash
# Check source permissions
ls -la /path/to/source/file

# Check destination permissions
ls -la /path/to/destination/

# Ensure write access to both
```

### Problem: Move Failed - File Exists

**Symptoms:**
- `FileExistsError` during move
- Destination already has file

**Solution:**
This is by design - tagslut uses move-only semantics and won't overwrite.
1. Review duplicates: `tagslut index check`
2. Quarantine duplicate: `tagslut execute quarantine-plan`
3. Or manually resolve

### Problem: Interrupted Move

**Symptoms:**
- Move operation stopped midway
- Some files moved, some not

**Solution:**
```bash
# Check move receipts
tagslut verify receipts --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# Review recovery status
tagslut verify recovery --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# See PROVENANCE_AND_RECOVERY.md for full recovery procedure
```

---

## Duration Issues

### Problem: Duration Mismatch

**Symptoms:**
- `duration-check` shows mismatches
- DJ safety concern

**Solution:**
```bash
# Get detailed audit
tagslut index duration-audit --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# If file duration is correct but reference is wrong:
tagslut index set-duration-ref --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# If file is corrupted:
# - Quarantine the file
# - Re-download from source
```

---

## CLI Issues

### Problem: Command Not Found

**Symptoms:**
- `tagslut: command not found`

**Solution:**
```bash
# Activate virtual environment
cd ~/Projects/tagslut
source .venv/bin/activate

# Verify installation
poetry install

# Try again
tagslut --help
```

### Problem: Using Retired Command

**Symptoms:**
- Error message about deprecated command
- Command doesn't exist

**Solution:**
These commands were retired on Feb 9, 2026:

| Old | New |
|-----|-----|
| `tagslut scan` | `tagslut index ...` |
| `tagslut recommend` | `tagslut decide plan ...` |
| `tagslut apply` | `tagslut execute move-plan ...` |
| `tagslut promote` | `tagslut execute promote-tags ...` |
| `tagslut quarantine` | `tagslut execute quarantine-plan ...` |
| `tagslut mgmt` | `tagslut index ... + tagslut report m3u ...` |
| `tagslut metadata` | `tagslut auth ... + tagslut index enrich ...` |
| `tagslut recover` | `tagslut verify recovery ... + tagslut report recovery ...` |

---

## File Issues

### Problem: File Not in Database

**Symptoms:**
- Pre-download check shows `keep` for files you know exist
- File not found during operations

**Solution:**
```bash
# Register the files
tagslut index register --zone library --recursive /path/to/files
```

### Problem: Metadata Not Matching

**Symptoms:**
- ISRC match fails
- Title/artist match fails
- File shows as `keep` when it should `skip`

**Solution:**
1. Check file tags: `python tools/review/dump_file_tags.py /path/to/file.flac`
2. Enrich metadata: `tagslut index enrich`
3. Re-run pre-download check

---

## Quick Diagnostic Commands

```bash
# Check environment
env | grep -E "(TAGSLUT|VOLUME)"

# Check database
sqlite3 ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db "SELECT COUNT(*) FROM files;"

# Check token status
tagslut auth status

# Check CLI works
tagslut --version

# List recent artifacts
ls -lt artifacts/ | head -10

# Check logs
tail -50 artifacts/moves_*.jsonl 2>/dev/null
```

## Getting Help

1. Check `docs/README_OPERATIONS.md` for operation reference
2. Check `docs/WORKFLOWS.md` for step-by-step guides
3. Check `docs/PROVENANCE_AND_RECOVERY.md` for recovery procedures
4. Run `tagslut <command> --help` for command-specific help
