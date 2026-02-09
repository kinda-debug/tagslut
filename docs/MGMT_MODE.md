# Management & Recovery Modes — dedupe CLI

> Status note (2026-02-08): This document contains both current behavior and historical design notes.
> For the authoritative command surface, run `poetry run dedupe mgmt --help` and see `docs/SCRIPT_SURFACE.md`.

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
dedupe mgmt [options]       # management & inventory
dedupe m [options]          # shorthand alias for mgmt
dedupe -m [options]         # shorthand flag for mgmt
dedupe recovery [options]   # file operations & library building
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
  --check-duration       Measure duration and set duration_status
  --audit-duration        Report duration_status anomalies
  --dj-only              Treat files as DJ material
  --set-duration-ref     Manually set a trusted duration reference

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

### Duration Safety (DJ Material)

For DJ material, duration must be validated against a trusted reference before promotion.
Size/format never override a duration mismatch.

New mgmt commands:
```bash
# Register + duration checks
dedupe mgmt register --source bpdl --dj-only --check-duration /path/to/downloads

# Re-check durations
dedupe mgmt check-duration /path/to/files --dj-only --execute

# Audit anomalies
dedupe mgmt audit-duration --dj-only --status warn,fail,unknown

# Manually set a trusted duration reference
dedupe mgmt set-duration-ref /path/to/file --dj-only --confirm --execute
```

Defaults (configurable):
- `ok` if |delta| ≤ 2000 ms
- `warn` if 2000 < |delta| ≤ 8000 ms
- `fail` if |delta| > 8000 ms

### M3U Generation

**Note:** M3U generation is handled by `dedupe mgmt`, NOT by BeatportDL. BeatportDL does not have a `--m3u` flag.

✅ `dedupe mgmt --m3u` is implemented.

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

  # Duration safety (DJ)
  --require-duration-ok  Block promotion unless duration_status is ok
  --allow-duration-warn  Allow warn status for manual override (never fail)
  --dj-only              Treat all targets as DJ material

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

-- Duration safety (DJ gating)
ALTER TABLE files ADD COLUMN is_dj_material INTEGER;     -- 1 for DJ material
ALTER TABLE files ADD COLUMN duration_ref_ms INTEGER;    -- trusted reference duration
ALTER TABLE files ADD COLUMN duration_ref_source TEXT;   -- beatport|manual|derived|unknown
ALTER TABLE files ADD COLUMN duration_ref_track_id TEXT; -- beatport_track_id or isrc
ALTER TABLE files ADD COLUMN duration_ref_updated_at TEXT;
ALTER TABLE files ADD COLUMN duration_measured_ms INTEGER;
ALTER TABLE files ADD COLUMN duration_measured_at TEXT;
ALTER TABLE files ADD COLUMN duration_delta_ms INTEGER;
ALTER TABLE files ADD COLUMN duration_status TEXT;       -- ok|warn|fail|unknown
ALTER TABLE files ADD COLUMN duration_check_version TEXT;

-- Reference duration cache
CREATE TABLE IF NOT EXISTS track_duration_refs (
  ref_id TEXT PRIMARY KEY,
  ref_type TEXT NOT NULL,          -- beatport|isrc|manual
  duration_ref_ms INTEGER NOT NULL,
  ref_source TEXT NOT NULL,        -- beatport|manual
  ref_updated_at TEXT
);
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

Duration-related events (JSONL):
```json
{
  "event": "duration_check",
  "timestamp": "2026-02-02T16:00:00Z",
  "path": "/staging/beatport/incoming/...",
  "source": "bpdl",
  "track_id": "beatport:1234567",
  "is_dj_material": true,
  "duration_ref_ms": 432000,
  "duration_measured_ms": 433500,
  "duration_delta_ms": 1500,
  "duration_status": "ok",
  "thresholds_ms": {"ok": 2000, "warn": 8000},
  "check_version": "duration_v1_ok2_warn8"
}
```
```json
{
  "event": "duration_anomaly",
  "timestamp": "2026-02-02T16:02:00Z",
  "path": "/staging/beatport/incoming/...",
  "track_id": "beatport:1234567",
  "is_dj_material": true,
  "duration_status": "fail",
  "duration_ref_ms": 420000,
  "duration_measured_ms": 452000,
  "duration_delta_ms": 32000,
  "action": "blocked_promotion"
}
```
```json
{
  "event": "promotion_decision",
  "timestamp": "2026-02-02T16:10:00Z",
  "duplicate_group_id": "dupgrp_1234",
  "is_dj_material": true,
  "chosen_track_path": "/accepted/DJ/Artist/...",
  "reason": "duration_ok_and_highest_trust_score",
  "alternatives": []
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

See `tools/beatportdl/bpdl/README.md` for full BeatportDL configuration reference.

Example wrapper script:
```bash
#!/bin/bash
# bpdl-wrapper.sh
bpdl "$@"
# Register downloads and generate M3U (M3U is a dedupe mgmt feature, not bpdl)
dedupe mgmt --source bpdl --register ~/Downloads/bpdl/
dedupe mgmt --m3u ~/Downloads/bpdl/
```

### qobuz-dl Integration

Similar pattern:
```bash
#!/bin/bash
# qobuz-wrapper.sh
qobuz-dl "$@"
dedupe mgmt --source qobuz --m3u --check ~/Downloads/qobuz/
```

### TIDDL (Tidal Downloader) Integration

TIDDL is a **system-installed** Tidal downloader. A wrapper script is provided at `tools/tiddl`.

**Wrapper details:**
- **Path**: `tools/tiddl`
- **Default binary**: `/opt/homebrew/bin/tiddl`
- **Override**: Set `TIDDL_BIN` environment variable

**Usage:**
```bash
# Download from Tidal (uses system-installed tiddl)
tools/tiddl <tidal-url>

# Override binary path if needed
TIDDL_BIN=/custom/path/tiddl tools/tiddl <tidal-url>

# Register to inventory and generate M3U
dedupe mgmt --source tidal --register ~/Downloads/tiddl/
dedupe mgmt --m3u ~/Downloads/tiddl/
```

**Key points:**
- No system binaries in repo — only the wrapper script
- M3U generation is handled by `dedupe mgmt --m3u`, NOT by TIDDL
- Use `--source tidal` when registering downloads

---

## Safety Guarantees

1. **No deletion**: Files are moved, never deleted
2. **Verified moves**: Hash checked before removing source
3. **Full logging**: Every operation recorded
4. **Dry-run default**: `--move` must be explicit
5. **Reversible**: Logs enable manual rollback if needed
6. **DJ duration gate**: DJ material is blocked from promotion if duration is not `ok`

---

## Unified Download Entrypoint: `tools/get`

The **preferred way** to download from Tidal or Beatport is via the unified `tools/get` script. It automatically routes URLs to the correct downloader based on domain.

```bash
# Tidal URLs → routed to tools/tiddl
tools/get https://tidal.com/browse/playlist/12345
tools/get https://listen.tidal.com/album/67890

# Beatport URLs → routed to tools/beatportdl/bpdl/bpdl
tools/get https://www.beatport.com/release/some-release/12345
tools/get https://www.beatport.com/track/some-track/67890

# Extra arguments are passed through to the underlying tool
tools/get https://tidal.com/browse/album/12345 --quality high
```

**Direct tool access** is still available if needed:

```bash
tools/tiddl <tidal-url>                    # Direct TIDDL access
tools/beatportdl/bpdl/bpdl <beatport-url>  # Direct BeatportDL access
```

---

## Standalone Workflow (No Database)

`tools/get` works completely independently—just grab tracks without any DB interaction:

```bash
# Just download, no tracking
tools/get https://www.beatport.com/release/some-release/12345
tools/get https://tidal.com/browse/album/67890

# Files land in the downloader's configured output directory
# (e.g., ~/Downloads/bpdl/ or ~/Downloads/tiddl/)
```

Use this when:
- Quick one-off downloads
- Testing/previewing before committing to library
- Downloads you don't need to track

---

## Integrated Workflow: Building a Sanitized Library

For full deduplication tracking and library management:

```
┌─────────────────────────────────────────────────────────────────┐
│  1. PRE-CHECK (optional, avoids re-downloading)                 │
│  dedupe mgmt --check --source tidal <url-or-path>               │
│  → "You already have this track from bpdl (2026-01-15)"         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. DOWNLOAD                                                    │
│  tools/get <url>                                                │
│  → files land in downloader's configured output dir             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. REGISTER (adds to inventory DB)                             │
│  dedupe mgmt --source tidal --register ~/Downloads/tiddl/       │
│  → hashes files, records provenance, flags duplicates           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. M3U GENERATION (for Roon import)                            │
│  dedupe mgmt --m3u ~/Downloads/tiddl/                           │
│  → creates playlist for immediate listening/review              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  5. PROMOTE TO LIBRARY (move-only)                              │
│  dedupe recovery --move --zone accepted --source tidal          │
│  → moves verified files to canonical structure                  │
└─────────────────────────────────────────────────────────────────┘
```

### Step-by-Step Commands

```bash
# 1. (Optional) Check if you already have these tracks
dedupe mgmt --check --source bpdl ~/queue.txt

# 2. Download from Beatport or Tidal
tools/get https://www.beatport.com/release/some-release/12345
tools/get https://tidal.com/browse/album/67890

# 3. Register to inventory, check for dupes
dedupe mgmt --source bpdl --register ~/Downloads/bpdl/
dedupe mgmt --source tidal --register ~/Downloads/tiddl/

# 4. Generate M3U playlist (this is a dedupe mgmt feature, NOT the downloaders)
dedupe mgmt --m3u ~/Downloads/bpdl/
dedupe mgmt --m3u ~/Downloads/tiddl/

# 5. Review M3U in Roon, verify tracks sound good

# 6. Move verified tracks to canonical library
dedupe recovery --move --zone accepted --source bpdl --since today
dedupe recovery --move --zone accepted --source tidal --since today
```

### Integration Points

| Step | Tool | DB Interaction |
|------|------|----------------|
| Pre-check | `dedupe mgmt --check` | Queries DB to avoid re-downloading |
| Download | `tools/get` | **None** — just a URL router |
| Register | `dedupe mgmt --register` | Adds files with source/date/hash |
| M3U | `dedupe mgmt --m3u` | Uses DB metadata for rich playlists |
| Promote | `dedupe recovery --move` | Uses DB to track verified files |

**Note:** BeatportDL does NOT have a `--m3u` flag. M3U generation is always done via `dedupe mgmt --m3u` or `tools/review/promote_by_tags.py`.

This workflow ensures:
- No accidental re-downloads
- Every file tracked in inventory
- Roon-ready playlists for immediate listening
- Clean, move-only path to canonical library

---

## DJ-Safe Beatport Playlist Promotion (Duration-First, Not Size-First)

1) Download (Beatport → staging):
```bash
bpdl --config ... "https://www.beatport.com/playlist/..."
```

2) Register + duration check (DJ-only):
```bash
dedupe mgmt register --source bpdl --dj-only --check-duration /staging/beatport/incoming
```

3) Audit duration anomalies:
```bash
dedupe mgmt audit-duration --dj-only --status warn,fail,unknown
```

4) Promote only duration-clean DJ tracks:
```bash
dedupe recovery --no-move --zone accepted --require-duration-ok --dj-only /staging/beatport/incoming
dedupe recovery --move    --zone accepted --require-duration-ok --dj-only /staging/beatport/incoming
```

Safety guarantees:
- No DJ track is promoted if its duration differs from the trusted reference by more than the configured threshold.
- Size/format never override a duration mismatch; they only break ties among duration-clean candidates.
- All duration checks and promotion decisions are logged in JSONL for audit.
