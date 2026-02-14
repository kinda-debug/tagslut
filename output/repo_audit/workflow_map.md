# Workflow Map

## Canonical CLI Surface

All new work MUST use these 7 commands:

```
tagslut intake    # Download/intake orchestration
tagslut index     # Library inventory & metadata
tagslut decide    # Policy-based planning
tagslut execute   # Execute plans
tagslut verify    # Validate operations
tagslut report    # Generate reports
tagslut auth      # Provider authentication
```

## Primary Workflows

### 1. Pre-Download Check (Beatport/Tidal)

**Purpose:** Check candidate downloads against DB before downloading.

```bash
# Check links file against DB
python tools/review/pre_download_check.py \
  --input ~/links.txt \
  --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --out-dir output/precheck

# Outputs:
# - precheck_decisions_<ts>.csv (per-track keep/skip + match method)
# - precheck_summary_<ts>.csv (per-link stats)
# - precheck_keep_track_urls_<ts>.txt (URLs for downloader)
```

### 2. Beatport Download (3-Command Workflow)

**Purpose:** Download from Beatport, merge into library.

```bash
# Option A: Full sync (download + merge)
tools/get-sync "https://www.beatport.com/release/..."

# Option B: Report only (no download)
tools/get-report "https://www.beatport.com/release/..."

# Option C: Unified router (routes by domain)
tools/get "https://www.beatport.com/release/..."
tools/get "https://tidal.com/browse/album/..."
```

### 3. Tidal Download

**Purpose:** Download from Tidal.

```bash
# Use tiddl directly or via router
tools/tiddl "https://tidal.com/browse/album/..."
# or
tools/get "https://tidal.com/browse/album/..."
```

### 4. Register New Files

**Purpose:** Add new files to database.

```bash
tagslut index register --zone staging --recursive /path/to/new/files
```

### 5. Duplicate Check

**Purpose:** Find duplicates in library.

```bash
tagslut index check --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
```

### 6. Duration Check

**Purpose:** Verify duration consistency (DJ safety).

```bash
tagslut index duration-check --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
tagslut index duration-audit --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
```

### 7. Metadata Enrichment

**Purpose:** Enrich files with provider metadata (ISRC, Beatport ID, etc).

```bash
# Enrich from indexed files
tagslut index enrich --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db

# OneTagger workflow (for ISRC tagging)
tools/tag-build --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
tools/tag-run --m3u output/onetagger_batch.m3u
# or combined:
tools/tag
```

### 8. Policy-Based Planning

**Purpose:** Generate execution plans based on policies.

```bash
tagslut decide profiles  # List available profiles
tagslut decide plan --profile default --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
```

### 9. Execute Plans

**Purpose:** Execute move/quarantine/promote operations.

```bash
# Execute move plan
tagslut execute move-plan --plan output/move_plan.json

# Execute quarantine
tagslut execute quarantine-plan --plan output/quarantine_plan.json

# Execute promote by tags (alternative path)
python tools/review/promote_by_tags.py --source /path --dest /path --move-log artifacts/moves.jsonl
```

### 10. Verification

**Purpose:** Validate operations completed correctly.

```bash
tagslut verify duration --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
tagslut verify recovery --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
tagslut verify parity --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
tagslut verify receipts --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
```

### 11. Reporting

**Purpose:** Generate operational reports.

```bash
tagslut report m3u --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
tagslut report duration --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
tagslut report recovery --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
tagslut report plan-summary --plan output/move_plan.json
```

### 12. Authentication

**Purpose:** Manage provider OAuth tokens.

```bash
tagslut auth status   # Show token status
tagslut auth init     # Initialize OAuth
tagslut auth refresh  # Refresh tokens
tagslut auth login    # Interactive login
```

## Retired Commands (DO NOT USE)

These were removed in Phase 5 (Feb 9, 2026):

| Retired | Replacement |
|---------|-------------|
| `dedupe scan` | `tagslut index ...` |
| `dedupe recommend` | `tagslut decide plan ...` |
| `dedupe apply` | `tagslut execute move-plan ...` |
| `dedupe promote` | `tagslut execute promote-tags ...` |
| `dedupe quarantine` | `tagslut execute quarantine-plan ...` |
| `dedupe mgmt` | `tagslut index ... + tagslut report m3u ...` |
| `dedupe metadata` | `tagslut auth ... + tagslut index enrich ...` |
| `dedupe recover` | `tagslut verify recovery ... + tagslut report recovery ...` |

## Operational Scripts (tools/review/)

These are direct Python scripts for specific operations:

| Script | Purpose | Status |
|--------|---------|--------|
| `pre_download_check.py` | Check candidate downloads against DB | Active |
| `promote_by_tags.py` | Move files using tag-based rules | Active |
| `move_from_plan.py` | Execute JSON move plans | Active |
| `quarantine_from_plan.py` | Execute quarantine operations | Active |
| `match_unknowns_to_epoch_2026_02_08_fast.py` | Match unknown tracks to epoch | Active |
| `backfill_metadata_from_epoch_2026_02_08.py` | Backfill metadata from epoch | Active |
| `duration_check_from_list.py` | Check durations from file list | Active |
| `export_track_table.py` | Export tracks to spreadsheet | Active |
| `fingerprint_report.py` | Generate FP analysis report | Active |
| `audio_analysis_report.py` | Audio health report | Active |
| `onetagger_workflow.py` | OneTagger symlink batch | Active |
| `beatport_prefilter.py` | Pre-filter Beatport downloads | Active |

## Data Flow

```
                    ┌─────────────────┐
                    │  Links File     │
                    │ (URLs to check) │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ pre_download_   │
                    │ check.py        │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
     ┌─────────────────┐           ┌─────────────────┐
     │   keep_urls.txt │           │  Skipped (in DB)│
     │   (download)    │           │                 │
     └────────┬────────┘           └─────────────────┘
              │
              ▼
     ┌─────────────────┐
     │ beatportdl/tiddl│
     │   (download)    │
     └────────┬────────┘
              │
              ▼
     ┌─────────────────┐
     │ tagslut index   │
     │ register        │
     └────────┬────────┘
              │
              ▼
     ┌─────────────────┐
     │ tagslut decide  │
     │ plan            │
     └────────┬────────┘
              │
              ▼
     ┌─────────────────┐
     │ tagslut execute │
     │ move-plan       │
     └────────┬────────┘
              │
              ▼
     ┌─────────────────┐
     │ tagslut verify  │
     │ (all checks)    │
     └────────┬────────┘
              │
              ▼
     ┌─────────────────┐
     │ Final Library   │
     └─────────────────┘
```

## Current Database

```
/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db
```

## Downloader Paths

```
Beatport: ~/Projects/beatportdl/beatportdl-darwin-arm64
Tidal: tiddl (in PATH or local)
```
