# Management & Recovery Modes — dedupe CLI

This document specifies the **`mgmt`** and **`recovery`** commands for the dedupe CLI, designed to support a controlled, inventory-driven workflow for building a clean, sanitized music library from fresh downloads.

**Important:** M3U playlist generation is a `dedupe mgmt` responsibility, NOT a BeatportDL feature. BeatportDL handles downloading and directory organization only.

---

## Philosophy

The goal is to **build a small, super-sanitized library from new downloads** rather than rescuing everything from legacy chaos. These modes support:

1. **Central inventory DB** tracking all audio files from multiple download sources
2. **Pre-download duplicate checking** to avoid re-downloading recent tracks
3. **Controlled file operations** with move-only semantics and full logging
4. **M3U playlist generation** for Roon-compatible import of new downloads

---

## Commands Overview

```
dedupe mgmt [options]       # -m shorthand — download management & inventory
dedupe recovery [options]   # -r shorthand — file operations & library building
```

---

## `dedupe mgmt` — Management Mode

Management mode intercepts and manages downloads from multiple sources (bpdl, qobuz-dl, tidal-dl, etc.).

### Core Responsibilities

1. **Maintain central inventory DB** of all audio files
2. **Check for duplicates/similar tracks** before downloading
3. **Generate M3U playlists** for downloaded content
4. **Prompt user** when similar files are found

### Flags & Options

```
dedupe mgmt [OPTIONS] [PATHS...]

Options:
  --db PATH              Path to inventory database (default: from config)
  --source NAME          Download source identifier (bpdl, qobuz, tidal, etc.)
  
  # Duplicate checking
  --check / --no-check   Enable/disable similarity check (default: --check)
  --threshold FLOAT      Similarity threshold 0.0-1.0 (default: 0.85)
  --prompt / --no-prompt Interactive prompt on similar match (default: --prompt)
  
  # M3U generation
  --m3u                  Generate Roon-compatible M3U playlist(s)
  --merge                Merge all items into single M3U (default: one per item)
  --m3u-dir PATH         Output directory for M3U files (default: same as downloads)
  
  # Inventory operations
  --register             Register files to inventory without moving
  --scan                 Scan and update inventory from paths
  --status               Show inventory statistics
  
  -v, --verbose          Verbose output
  --dry-run              Show what would happen without changes
```

### Similarity Check Workflow

When `--check` is enabled (default), before any download:

1. Query inventory DB for tracks with similar:
   - Artist + Title (fuzzy match)
   - ISRC (exact match)
   - Audio fingerprint (if available)
   
2. If match found with confidence ≥ threshold:
   - Display diagnosis:
     ```
     ⚠️  Similar track found in inventory:
     
     EXISTING: /path/to/Artist - Track.flac
       Source: bpdl (2026-01-15)
       Quality: FLAC 44.1kHz/16bit, 4:32
       Tags: complete (ISRC, BPM, key)
     
     NEW:      Artist - Track (from qobuz)
       Quality: FLAC 96kHz/24bit, 4:32
       
     [S]kip  [D]ownload anyway  [R]eplace  [Q]uit
     ```
   
3. If `--no-prompt`, log and skip by default

#TODO: Implement interactive prompt when similar files exist (skip/download/replace)
#TODO: Log every decision (checks, waivers, skips) to JSON audit log

### M3U Generation

**Note:** M3U generation is handled by `dedupe mgmt`, NOT by BeatportDL. BeatportDL does not have a `--m3u` flag.

#TODO: Implement M3U generation in `dedupe mgmt --m3u`

The `--m3u` flag generates Roon-compatible M3U playlists:

```bash
# One M3U per download item (album/release)
dedupe mgmt --m3u --source bpdl /path/to/downloads

# Single merged M3U for entire session
dedupe mgmt --m3u --merge --source bpdl /path/to/downloads
```

M3U format (Roon-compatible extended M3U):
```m3u
#EXTM3U
#PLAYLIST:bpdl-2026-02-01
#EXTART:Various Artists
#EXTINF:272,Artist - Track Title
/absolute/path/to/file.flac
```

### Example Workflows

```bash
# Register new bpdl downloads to inventory
dedupe mgmt --source bpdl --register ~/Downloads/bpdl/

# Generate M3U for registered downloads (separate step)
dedupe mgmt --m3u ~/Downloads/bpdl/

# Check if tracks exist before qobuz download
dedupe mgmt --check --source qobuz --dry-run ~/queue.txt

# Scan existing library into inventory
dedupe mgmt --scan --source legacy /Volumes/Music/
```

---

## `dedupe recovery` — Recovery Mode

Recovery mode handles actual file operations: moving, renaming, and organizing files into the canonical library structure.

### Core Responsibilities

1. **Move files** from staging to canonical locations
2. **Rename files** according to naming conventions
3. **Log all operations** for auditability
4. **Support dry-run** for safe preview

### Flags & Options

```
dedupe recovery [OPTIONS] [PATHS...]

Options:
  --db PATH              Path to inventory database (default: from config)
  
  # File operations
  --move                 Actually move files (default: dry-run/no-move)
  --no-move              Dry-run mode, log only (default)
  --rename-only          Rename in place, no relocation
  
  # Targets
  --dest PATH            Destination root for moves
  --zone ZONE            Target zone (accepted, staging, etc.)
  
  # Filtering
  --source NAME          Filter by download source
  --since DATE           Filter by registration date
  --status STATUS        Filter by file status (new, verified, etc.)
  
  # Logging
  --log PATH             Operation log file (default: recovery-YYYY-MM-DD.log)
  --log-format FMT       Log format: json, tsv, plain (default: json)
  
  -v, --verbose          Verbose output
  --dry-run              Alias for --no-move
```

### Move-Only Policy

**All file operations use MOVE semantics:**

- Source file is removed only after verified move
- No duplicate copies left behind
- Temporary staging allowed but cleaned after success
- Every operation logged with before/after paths

### Rename-Only Pass

The `--rename-only` flag renames files in place without relocating:

```bash
# Preview renames
dedupe recovery --rename-only --dry-run /path/to/files/

# Execute renames
dedupe recovery --rename-only --move /path/to/files/
```

Rename rules (configurable):
- `{artist} - {title}.flac` (default)
- Sanitize special characters
- Normalize Unicode
- Truncate to filesystem limits

### Example Workflows

```bash
# Preview what would be moved from staging to accepted
dedupe recovery --no-move --zone accepted /Volumes/Music/staging/

# Actually move verified files
dedupe recovery --move --zone accepted --status verified /Volumes/Music/staging/

# Rename-only pass on existing library
dedupe recovery --rename-only --move /Volumes/Music/accepted/

# Move recent bpdl downloads to canonical location
dedupe recovery --move --source bpdl --since 2026-01-01 --dest /Volumes/Music/accepted/
```

---

## Inventory Database Schema

The central inventory DB extends the existing `files` table:

```sql
-- Core inventory fields
ALTER TABLE files ADD COLUMN download_source TEXT;      -- bpdl, qobuz, tidal, legacy
ALTER TABLE files ADD COLUMN download_date TEXT;        -- ISO timestamp
ALTER TABLE files ADD COLUMN original_path TEXT;        -- path at registration
ALTER TABLE files ADD COLUMN canonical_path TEXT;       -- final destination (if moved)

-- Similarity/dedup fields  
ALTER TABLE files ADD COLUMN isrc TEXT;
ALTER TABLE files ADD COLUMN fingerprint TEXT;          -- chromaprint or similar
ALTER TABLE files ADD COLUMN fingerprint_version TEXT;

-- M3U tracking
ALTER TABLE files ADD COLUMN m3u_exported TEXT;         -- ISO timestamp of last M3U export
ALTER TABLE files ADD COLUMN m3u_path TEXT;             -- path to M3U containing this file

-- Status tracking
ALTER TABLE files ADD COLUMN mgmt_status TEXT;          -- new, checked, verified, moved
ALTER TABLE files ADD COLUMN mgmt_notes TEXT;           -- human-readable notes
```

---

## Logging Format

All operations are logged in JSON format by default:

```json
{
  "timestamp": "2026-02-01T14:30:00Z",
  "operation": "move",
  "source": "/staging/Artist - Track.flac",
  "destination": "/accepted/Artist/Album/Track.flac",
  "status": "success",
  "file_hash": "abc123...",
  "download_source": "bpdl",
  "verified": true
}
```

TSV format for spreadsheet import:
```
timestamp	operation	source	destination	status	file_hash
2026-02-01T14:30:00Z	move	/staging/...	/accepted/...	success	abc123...
```

---

## Configuration

Add to `config.toml`:

```toml
[mgmt]
# Default inventory database
db = "/path/to/inventory.db"

# Similarity threshold (0.0-1.0)
similarity_threshold = 0.85

# Default M3U output directory
m3u_dir = "~/Music/Playlists/imports"

# Prompt on similar match
prompt_on_similar = true

[recovery]
# Default destination for moves
default_dest = "/Volumes/Music/accepted"

# Log directory
log_dir = "~/.dedupe/logs"

# Naming template
name_template = "{artist} - {title}"
```

---

## Integration with Download Tools

### bpdl (BeatportDL) Integration

BeatportDL is an **upstream download tool** that feeds the dedupe pipeline. It handles:
- Downloading tracks from Beatport with rich metadata
- Directory organization via `sort_by_context` and `*_directory_template` settings
- Filename formatting via `track_file_template`

**BeatportDL does NOT generate M3U playlists.** M3U generation is handled by `dedupe mgmt --m3u` after downloads are registered.

bpdl should be configured to:
1. Output to a staging directory monitored by `dedupe mgmt`
2. Use `sort_by_context: true` for organized directory output
3. Set appropriate `*_directory_template` values for releases, playlists, charts, labels, artists

See `postman/bpdl/README.md` for full BeatportDL configuration reference.

Example wrapper script:
```bash
#!/bin/bash
# bpdl-wrapper.sh
bpdl "$@"
# Register downloads and generate M3U (M3U is a dedupe mgmt feature, not bpdl)
dedupe mgmt --source bpdl --register ~/Downloads/bpdl/
dedupe mgmt --m3u ~/Downloads/bpdl/
```

### qobuz-dl / tidal-dl Integration

Similar pattern:
```bash
#!/bin/bash
# qobuz-wrapper.sh
qobuz-dl "$@"
dedupe mgmt --source qobuz --m3u --check ~/Downloads/qobuz/
```

---

## Safety Guarantees

1. **No deletion**: Files are moved, never deleted
2. **Verified moves**: Hash checked before removing source
3. **Full logging**: Every operation recorded
4. **Dry-run default**: `--move` must be explicit
5. **Reversible**: Logs enable manual rollback if needed

---

## Typical Workflow: Building a Sanitized Library

```bash
# 1. Download from Beatport (directory layout controlled by sort_by_context and *_directory_template)
bpdl <urls>

# 2. Register to inventory, check for dupes
dedupe mgmt --source bpdl --check ~/Downloads/bpdl/

# 3. Generate M3U playlist (this is a dedupe mgmt feature, NOT bpdl)
dedupe mgmt --m3u ~/Downloads/bpdl/

# 4. Review M3U in Roon, verify tracks sound good

# 5. Move verified tracks to canonical library
dedupe recovery --move --zone accepted --source bpdl --since today

# 6. Repeat with other sources (qobuz, tidal)
```

**Note:** BeatportDL does NOT have a `--m3u` flag. M3U generation is always done via `dedupe mgmt --m3u` or `tools/review/promote_by_tags.py`.

This workflow ensures:
- No accidental re-downloads
- Every file tracked in inventory
- Roon-ready playlists for immediate listening
- Clean, move-only path to canonical library
