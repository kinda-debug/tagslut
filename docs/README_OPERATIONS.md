# tagslut Operations Manual

**Version:** 2.0.0
**Last Updated:** 2026-02-14

This is the single source of truth for operating the tagslut music library automation toolkit.

## Quick Start

```bash
# Activate environment
cd ~/Projects/dedupe
source .venv/bin/activate

# Verify CLI works
tagslut --help
```

## Current Database

```
/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
```

## Canonical CLI Commands

All operations use these 7 command groups:

| Command | Purpose |
|---------|---------|
| `tagslut intake` | Download/intake orchestration |
| `tagslut index` | Library inventory & metadata |
| `tagslut decide` | Policy-based planning |
| `tagslut execute` | Execute plans |
| `tagslut verify` | Validate operations |
| `tagslut report` | Generate reports |
| `tagslut auth` | Provider authentication |

## Most Common Operations

### 1. Check Links Before Download

Check if tracks from Beatport/Tidal links already exist in your library:

```bash
# Create a file with URLs (one per line)
cat > ~/links.txt << 'EOF'
https://www.beatport.com/release/example/12345
https://tidal.com/browse/album/67890
EOF

# Run pre-download check
python tools/review/pre_download_check.py \
  --input ~/links.txt \
  --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --out-dir output/precheck
```

**Outputs:**
- `precheck_decisions_<ts>.csv` - Per-track keep/skip with match method
- `precheck_summary_<ts>.csv` - Per-link statistics
- `precheck_keep_track_urls_<ts>.txt` - URLs for downloader (tracks NOT in library)

### 2. Download from Beatport

```bash
# Full sync (download missing + merge M3U)
tools/get-sync "https://www.beatport.com/release/example/12345"

# Report only (no download)
tools/get-report "https://www.beatport.com/release/example/12345"
```

**Note:** Beatport downloads work without interactive OAuth - uses stored config.

### 3. Download from Tidal

```bash
# Using router
tools/get "https://tidal.com/browse/album/67890"

# Or direct
tools/tiddl "https://tidal.com/browse/album/67890"
```

**Note:** Requires valid Tidal token. Check with `tagslut auth status`.

### 4. Download from Deezer

```bash
# Via router (auto FLAC + auto-register source=deezer)
tools/get "https://www.deezer.com/en/track/3451496391"

# Or direct wrapper
tools/deemix "https://www.deezer.com/en/track/3451496391"
```

**Defaults:** downloads to `~/Music/mdl/deezer`, bitrate `FLAC`, then runs `tagslut index register --source deezer --execute`.

### 5. Register New Files

```bash
tagslut index register \
  --zone staging \
  --recursive \
  /path/to/new/files
```

### 6. Check for Duplicates

```bash
tagslut index check \
  --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
```

### 7. Duration Check (DJ Safety)

```bash
# Quick check
tagslut index duration-check \
  --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db

# Full audit
tagslut index duration-audit \
  --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
```

### 7. Generate Execution Plan

```bash
# List available profiles
tagslut decide profiles

# Generate plan
tagslut decide plan \
  --profile default \
  --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --output output/move_plan.json
```

### 8. Execute Plan

```bash
# Execute move plan
tagslut execute move-plan \
  --plan output/move_plan.json

# Or use direct script
python tools/review/promote_by_tags.py \
  --source /path/to/staging \
  --dest /path/to/library \
  --move-log artifacts/moves.jsonl
```

### 9. Verify Operations

```bash
# All verifications
tagslut verify duration --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
tagslut verify recovery --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
tagslut verify receipts --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
```

### 10. Generate Reports

```bash
# M3U playlist
tagslut report m3u --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db

# Duration report
tagslut report duration --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
```

## What Each Command Writes

| Command | Writes To |
|---------|-----------|
| `tagslut index register` | `files` table in DB |
| `tagslut index check` | `duplicates` table in DB |
| `tagslut index duration-check` | Console output only |
| `tagslut index enrich` | `metadata_json` column in DB |
| `tagslut decide plan` | JSON file (--output) |
| `tagslut execute move-plan` | Moves files + `moves` table in DB + JSONL log |
| `tagslut verify *` | Console output only |
| `tagslut report *` | Output files (M3U, CSV, MD) |
| `pre_download_check.py` | CSV + TXT files in --out-dir |

## Safe vs Unsafe Operations

### Safe (Read-Only)

- `tagslut index check`
- `tagslut index duration-check`
- `tagslut index duration-audit`
- `tagslut verify *`
- `tagslut report *`
- `tagslut auth status`
- `tagslut decide plan`
- `pre_download_check.py`
- `tools/get-report`

### Modifies Database Only

- `tagslut index register`
- `tagslut index enrich`
- `tagslut index set-duration-ref`

### Moves Files + Modifies Database

- `tagslut execute move-plan`
- `tagslut execute quarantine-plan`
- `tagslut execute promote-tags`
- `tools/review/promote_by_tags.py`
- `tools/review/move_from_plan.py`
- `tools/review/quarantine_from_plan.py`

### Downloads Files

- `tools/get` (unified router)
- `tools/get-sync` (Beatport)
- `tools/get-auto` (precheck + download missing)
- `tools/tiddl` (Tidal)
- `tools/deemix` (Deezer, auto-registers)

## DO NOT USE (Retired)

These commands were retired on Feb 9, 2026:

| Retired | Use Instead |
|---------|-------------|
| `dedupe scan` | `tagslut index ...` |
| `dedupe recommend` | `tagslut decide plan ...` |
| `dedupe apply` | `tagslut execute move-plan ...` |
| `dedupe promote` | `tagslut execute promote-tags ...` |
| `dedupe quarantine` | `tagslut execute quarantine-plan ...` |
| `dedupe mgmt` | `tagslut index ... + tagslut report m3u ...` |
| `dedupe metadata` | `tagslut auth ... + tagslut index enrich ...` |
| `dedupe recover` | `tagslut verify recovery ... + tagslut report recovery ...` |

**Note:** `dedupe` as an alias for `tagslut` still works, but use `tagslut` for new work.

## Downloader Locations

```
Beatport: tools/beatportdl/bpdl/bpdl (or ~/Projects/beatportdl/beatportdl-darwin-arm64)
Tidal:    tiddl (via PATH or tools/tiddl)
Deezer:   deemix (via PATH or tools/deemix)
```

## Environment Variables

Set in `.env`:

```
DEDUPE_DB=/path/to/music.db
VOLUME_LIBRARY=/path/to/library
VOLUME_STAGING=/path/to/staging
VOLUME_ARCHIVE=/path/to/archive
VOLUME_QUARANTINE=/path/to/quarantine
DEDUPE_ARTIFACTS=/path/to/artifacts
```

## Getting Help

```bash
# CLI help
tagslut --help
tagslut index --help
tagslut execute --help

# Policy docs
cat docs/SURFACE_POLICY.md
cat docs/SCRIPT_SURFACE.md
```

## Related Documentation

- `docs/WORKFLOWS.md` - Detailed workflow guides
- `docs/TROUBLESHOOTING.md` - Common issues and fixes
- `docs/PROVENANCE_AND_RECOVERY.md` - Recovery procedures
- `docs/ZONES.md` - Zone system explanation
