<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

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
lsof +D $REPO_ROOT_db/

# Kill any stale processes
# Then retry operation
```

### Problem: Database Not Found

**Symptoms:**
- `DB not found: /path/to/music.db`

**Solution:**
```bash
# Check the path exists
ls -la $TAGSLUT_DB

# Check .env configuration
cat .env | grep TAGSLUT_DB

# Or config.toml db.path
cat config.toml | grep -n "db"
```

---

## Pre-Download Check Issues

### Problem: `tools/get` skips everything

**Symptoms:**
- Output says all candidates already have same-or-better matches
- No download starts

**Solution:**
```bash
# Inspect current precheck behavior explicitly
python tools/review/pre_download_check.py --input "<url>"

# Intentionally bypass precheck if needed
tools/get "<url>" --no-precheck

# Or still download matched tracks
tools/get "<url>" --force-download
```

Notes:
- `--force-download` only affects the download decision. It does not make a lower-quality incoming file replace an equal-or-better library file.
- salvageable metadata/tag issues go to `FIX_ROOT` (default: `/Volumes/MUSIC/_work/fix`)
- risky files go to `QUARANTINE_ROOT` / `$VOLUME_QUARANTINE` (default: `/Volumes/MUSIC/_work/quarantine`)
- deterministic `dest_exists` duplicates go to `DISCARD_ROOT` (default: `/Volumes/MUSIC/_work/discard`)

### Problem: Extract Script Not Found

**Symptoms:**
- `Extract script not found: /path/to/extract_tracklists_from_links.py`

**Solution:**
```bash
# Run from repo root
cd $REPO_ROOT
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
2. Deterministic duplicates should go to `DISCARD_ROOT`, not quarantine
3. Use quarantine only for genuinely risky files

### Problem: Sidecar files did not land where expected

**Symptoms:**
- audio move succeeded
- adjacent lyric or artwork files were skipped or not present at destination

**Solution:**
`tagslut execute move-plan` now attempts common sidecars automatically, but it still uses skip-on-collision behavior.
1. Check whether sibling files actually existed next to the source audio
2. Review the move summary for companion `skip_dest_exists` results
3. Re-run after resolving the destination collision if the sidecar must move

### Problem: Interrupted Move

**Symptoms:**
- Move operation stopped midway
- Some files moved, some not

**Solution:**
```bash
# Check move receipts
tagslut verify receipts --db $TAGSLUT_DB

# Recovery workflow is retired
# Historical recovery procedure lives under legacy/tagslut_recovery/
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
tagslut index duration-audit --db $TAGSLUT_DB

# If file duration is correct but reference is wrong:
tagslut index set-duration-ref --db $TAGSLUT_DB

# If file is corrupted:
# - Quarantine the file
# - Re-download from source
```

---

## CLI Issues

### Problem: `process-root` rejects scan phases on a v3 DB

**Symptoms:**
- error mentions `v3 DB guard`
- `register`, `integrity`, or `hash` were requested through `process-root`

**Solution:**
```bash
# Use only the v3-safe staged-root phases
python -m tagslut intake process-root \
  --db "$V3_DB" \
  --root "$PROMOTE_ROOT" \
  --library "$MASTER_LIBRARY" \
  --phases identify,enrich,art,promote,dj
```

If you intentionally need register or integrity behavior, run the dedicated commands (`tagslut index register`, `tools/review/check_integrity_update_db.py`) instead of `process-root`.

### Problem: Essentia not found during DJ phase

**Symptoms:**
- warning mentions `Essentia not found`
- BPM/key fallback analysis is skipped for staged FLACs

**Solution:**
```bash
# macOS
brew install essentia
```

If Essentia is unavailable, the DJ phase can still use canonical BPM/key already present in v3 identity data.

### Problem: Command Not Found

**Symptoms:**
- `tagslut: command not found`

**Solution:**
```bash
# Activate virtual environment
cd $REPO_ROOT
source .venv/bin/activate

# Verify installation
poetry install

# Try again
tagslut --help
```

### Problem: Using Retired Command

**Symptoms:**
- Error message about deprecated command

---

## DJ Export Issues

### Problem: `tagslut dj export` appears to hang during transcode

**Symptoms:**
- No progress output after "Starting transcode..."
- One or more ffmpeg jobs never return

**Solution:**
```bash
# Set a hard timeout for ffmpeg (seconds)
export DJ_TRANSCODE_TIMEOUT_S=900

# Re-run export
tagslut dj export --input-xlsx $DJ_XLSX --output-root $DJ_USB_ROOT

# Or pass a per-run timeout
tagslut dj export --input-xlsx $DJ_XLSX --output-root $DJ_USB_ROOT --transcode-timeout-s 900
```
To stop immediately on the first failure:
```bash
tagslut dj export --input-xlsx $DJ_XLSX --output-root $DJ_USB_ROOT --fail-fast
```
If timeouts persist, check the specific source files and re-run with a smaller batch.

Artifacts:
- `export_manifest.jsonl` includes per-track status and error details.
- `export_failures.jsonl` is written when any tracks fail or time out.

For v3 DJ pool builds (`scripts/dj/build_pool_v3.py`), failures are logged to:
- `export_failures.jsonl` under the pool output root when `--execute` is used.
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
| `tagslut recover` | Retired; see `legacy/tagslut_recovery/` for the archived workflow |

Retention cleanup:
```bash
python tools/review/quarantine_gc.py \
  --root "$QUARANTINE_ROOT" \
  --days "$QUARANTINE_RETENTION_DAYS"
```

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
sqlite3 $TAGSLUT_DB "SELECT COUNT(*) FROM files;"

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

1. Check `docs/OPERATIONS.md` for operation reference
2. Check `docs/WORKFLOWS.md` for step-by-step guides
3. Check `docs/ARCHITECTURE.md` for recovery procedures
4. Run `tagslut <command> --help` for command-specific help
