# dedupe mgmt Quick Reference

## Commands

### `dedupe mgmt register`
Register downloaded files in inventory.

```bash
# Dry-run (see what would happen, don't save)
dedupe mgmt register /path/to/downloads --source bpdl

# Execute (actually save to database)
dedupe mgmt register /path/to/downloads --source bpdl --execute

# Verbose (show each file processed)
dedupe mgmt register /path/to/downloads --source bpdl --execute -v

# Use custom database
dedupe mgmt register /path/to/downloads --source bpdl --db /path/to/music.db --execute
```

**Options**:
- `PATH` - Directory containing FLAC files (required)
- `--source` - Download source: bpdl, tidal, qobuz, legacy (required)
- `--db` - Database path (auto-detected from $DEDUPE_DB if not provided)
- `--execute` - Actually save to database (default: dry-run)
- `-v, --verbose` - Verbose output

**What it does**:
1. Scans directory recursively for .flac files
2. Computes SHA256 checksum for each
3. Extracts duration from FLAC metadata
4. Checks if already registered (skips if so)
5. Inserts into database with source tracking

**Database fields populated**:
- `download_source` - The source you specified
- `download_date` - ISO timestamp
- `original_path` - File path before any moves
- `mgmt_status` - Set to "new"
- `sha256` - Computed checksum
- `duration` - Extracted from metadata

---

### `dedupe mgmt check`
Detect duplicate files before downloading.

```bash
# Check a directory
dedupe mgmt check /path/to/downloads --source bpdl

# Check with stdin
find ~/incoming -name "*.flac" | dedupe mgmt check --source tidal

# Strict mode (reject if same file exists from ANY source)
dedupe mgmt check /path/to/downloads --strict

# Verbose (show which files are safe/conflicts)
dedupe mgmt check /path/to/downloads --source bpdl -v

# Use custom database
dedupe mgmt check /path/to/downloads --source bpdl --db /path/to/music.db
```

**Options**:
- `PATH` - Directory to check (optional if using stdin)
- `--source` - Filter by source (optional)
- `--db` - Database path (auto-detected if not provided)
- `--strict` - Strict mode (any match = conflict)
- `-v, --verbose` - Verbose output

**What it does**:
1. Scans directory or reads from stdin
2. Computes SHA256 for each file
3. Queries database for matching checksums
4. Reports unique vs. duplicate files
5. With --verbose, shows which files exist and where

**Output**:
```
==================================================
RESULTS
==================================================
  Total:             3
  Unique:            2  ✓ (safe to download)
  Duplicates:        1  ⚠ (already exists)
  Errors:            0
```

---

## Workflow Examples

### Scenario 1: Download from Beatport, avoid duplicates

```bash
# Download tracks
tools/get https://www.beatport.com/release/xyz/123456

# Check before registering
dedupe mgmt check ~/Downloads/bpdl --source bpdl

# If unique, register
dedupe mgmt register ~/Downloads/bpdl --source bpdl --execute

# If conflicts, skip those files and only register unique ones
# (Future: interactive prompt will handle this automatically)
```

### Scenario 2: Import legacy files

```bash
# Register legacy collection
dedupe mgmt register /old/music --source legacy --execute

# Check if any are already in newer downloads
dedupe mgmt check /old/music --db music.db

# Duplicates can be skipped or moved to "duplicate" folder
# (Future: dedupe recovery --move will handle this)
```

### Scenario 3: Multi-source fallback

```bash
# Download from Beatport first
tools/get https://www.beatport.com/release/xyz/123456
dedupe mgmt register ~/Downloads/bpdl --source bpdl --execute

# Then try Tidal (using source filter, won't conflict on same file)
tools/get https://tidal.com/browse/album/987654
dedupe mgmt check ~/Downloads/tiddl --source tidal  # Will be unique!
dedupe mgmt register ~/Downloads/tiddl --source tidal --execute

# Now you have both sources for the same album
# Later, you can choose which version to keep
```

---

## Database Queries

View what's been registered:

```bash
# Show all downloaded files
sqlite3 music.db "SELECT path, download_source, mgmt_status FROM files WHERE download_source IS NOT NULL ORDER BY download_date DESC"

# Show files by source
sqlite3 music.db "SELECT path FROM files WHERE download_source='bpdl' ORDER BY download_date DESC"

# Find files registered in last 7 days
sqlite3 music.db "SELECT path, download_source FROM files WHERE download_date >= datetime('now', '-7 days') ORDER BY download_date DESC"

# Find duplicate SHA256 across multiple sources
sqlite3 music.db "SELECT sha256, COUNT(*) as count, GROUP_CONCAT(DISTINCT download_source) as sources FROM files WHERE download_source IS NOT NULL GROUP BY sha256 HAVING count > 1"
```

---

## Common Issues

### "Database not found"
Make sure your database exists or set `$DEDUPE_DB` environment variable:
```bash
export DEDUPE_DB=/path/to/music.db
dedupe mgmt register ~/Downloads/bpdl --source bpdl --execute
```

### "No FLAC files found"
Check directory path and file extensions:
```bash
# Debug: find FLAC files manually
find ~/Downloads/bpdl -name "*.flac" -type f

# Then try register again
dedupe mgmt register ~/Downloads/bpdl --source bpdl -v
```

### "File already registered"
Files are skipped if they have the same path in the database. To re-register:
1. Remove from database: `sqlite3 music.db "DELETE FROM files WHERE path LIKE '%filename%'"`
2. Re-run register with `--execute`

### "Check shows all files as duplicates"
This usually means the files were already registered from the same source. Use:
```bash
# See what's already in database
sqlite3 music.db "SELECT COUNT(*) FROM files WHERE download_source='bpdl'"

# Check with verbose to see which files conflict
dedupe mgmt check /path/to/downloads --source bpdl -v
```

---

## Integration with Other Tools

### With `tools/get` (unified downloader)
```bash
# Download
tools/get https://www.beatport.com/release/xyz/123
tools/get https://tidal.com/browse/album/456

# Check and register
dedupe mgmt check ~/Downloads/bpdl --source bpdl
dedupe mgmt register ~/Downloads/bpdl --source bpdl --execute
```

### With `dedupe scan` (file scanning)
```bash
# First register downloads
dedupe mgmt register ~/Downloads/bpdl --source bpdl --execute

# Then scan the library
dedupe scan /Volumes/DJSSD/EM/Archive
```

### With `dedupe recovery` (future: moving files)
```bash
# Register
dedupe mgmt register ~/Downloads/bpdl --source bpdl --execute

# Later: move to canonical location
dedupe recovery --move ~/Downloads/bpdl --db music.db
```

### With `Yate` (manual tagging)
```bash
# Register with source
dedupe mgmt register ~/Downloads/bpdl --source bpdl --execute

# Manually tag in Yate
open -a Yate ~/Downloads/bpdl

# No re-registration needed - database already has them!
```

---

## Advanced Usage

### Strict mode for paranoid users
```bash
# Reject if exact same file exists anywhere (any source)
dedupe mgmt check ~/Downloads --strict --db music.db
```

### Custom database per project
```bash
# Download for DJ Set A
tools/get https://www.beatport.com/release/set-a/123
dedupe mgmt register ~/Downloads/bpdl --source bpdl --db ~/dj-set-a.db --execute

# Download for DJ Set B
tools/get https://www.beatport.com/release/set-b/456
dedupe mgmt register ~/Downloads/bpdl --source bpdl --db ~/dj-set-b.db --execute
```

### Batch processing with find
```bash
# Register all subdirectories
for dir in ~/Downloads/*/; do
  source=$(basename "$dir")
  echo "Registering $source..."
  dedupe mgmt register "$dir" --source "$source" --execute
done
```

---

## FAQ

**Q: What's the difference between --source and database?**
A: `--source` tags WHERE the file came from (Beatport/Tidal/etc). The `--db` is just which database file to use for storage.

**Q: Can I register the same file with different sources?**
A: Yes! The database stores both with the same SHA256 but different `download_source` values. Later, you can choose which version to keep.

**Q: What if a file is corrupted during download?**
A: Register anyway. If corruption is detected by `flac -t`, the file will be marked accordingly. The `dedupe recovery` command will handle repair.

**Q: Can I delete registered files?**
A: Yes, delete the files from disk. The database entries remain (for audit). To clean up database, run:
```bash
sqlite3 music.db "DELETE FROM files WHERE path NOT LIKE '/%%' OR NOT EXISTS (SELECT 1 FROM files f WHERE f.path = path)"
```

**Q: What's the difference between check and recovery?**
A: `check` detects duplicates BEFORE downloading. `recovery` (future) actually moves files to canonical locations AFTER downloading.

---

## Next Steps

- ✅ Phase 1: **dedupe mgmt** (you are here)
- ⏳ Phase 2: **dedupe recovery** (move files with safety checks)
- ⏳ Phase 3: **M3U generation**, **automation**, **Yate integration**

See [ACTION_PLAN.md](ACTION_PLAN.md) for full roadmap.
