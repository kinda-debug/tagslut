# Workflows

Complete step-by-step workflows for common operations.

## Workflow 1: Pre-Download Check + Beatport Download

**Goal:** Check a list of Beatport links against your library, then download only missing tracks.

### Step 1: Create Links File

```bash
cat > ~/beatport_links.txt << 'EOF'
https://www.beatport.com/release/example-release/12345
https://www.beatport.com/chart/my-chart/67890
https://www.beatport.com/track/some-track/11111
EOF
```

### Step 2: Run Pre-Download Check

```bash
cd ~/Projects/tagslut
source .venv/bin/activate

python tools/review/pre_download_check.py \
  --input ~/beatport_links.txt \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --out-dir output/precheck
```

### Step 3: Review Results

```bash
# Check decisions
cat output/precheck/precheck_decisions_*.csv | head -20

# Check summary
cat output/precheck/precheck_summary_*.csv

# Count keep vs skip
grep -c ",keep," output/precheck/precheck_decisions_*.csv
grep -c ",skip," output/precheck/precheck_decisions_*.csv
```

### Step 4: Download Missing Tracks

```bash
# Get the keep URLs file
KEEP_FILE=$(ls -t output/precheck/precheck_keep_track_urls_*.txt | head -1)

# Download each track
while read -r url; do
  ~/Projects/beatportdl/beatportdl-darwin-arm64 "$url"
done < "$KEEP_FILE"
```

### Step 5: Register Downloaded Files

```bash
tagslut index register \
  --zone staging \
  --recursive \
  /path/to/downloaded/files
```

---

## Workflow 2: Pre-Download Check + Tidal Download

**Goal:** Check Tidal links against your library, then download only missing tracks.

### Step 1: Ensure Tidal Token is Valid

```bash
tagslut auth status
# If expired:
tagslut auth refresh
```

### Step 2: Create Links File

```bash
cat > ~/tidal_links.txt << 'EOF'
https://tidal.com/browse/album/123456789
https://tidal.com/browse/playlist/abc-def-123
EOF
```

### Step 3: Run Pre-Download Check

```bash
python tools/review/pre_download_check.py \
  --input ~/tidal_links.txt \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --out-dir output/precheck
```

### Step 4: Download Missing Tracks

```bash
KEEP_FILE=$(ls -t output/precheck/precheck_keep_track_urls_*.txt | head -1)

while read -r url; do
  tools/tiddl "$url"
done < "$KEEP_FILE"
```

---

## Workflow 2a: Automatic Precheck + Download (Any Source)

**Goal:** One-command flow to check DB and download only missing tracks.

```bash
# Single URL
tools/get-auto "https://www.beatport.com/release/example/12345"

# Multiple URLs
tools/get-auto \
  "https://www.beatport.com/release/a/1" \
  "https://tidal.com/browse/album/2" \
  "https://deezer.com/album/3"

# From file
tools/get-auto --links-file ~/links.txt
```

**What happens:**
1. Runs `pre_download_check.py` against DB
2. Generates keep/skip decisions
3. Downloads only missing tracks via `tools/get`
4. Deezer downloads auto-register; others need manual registration

---

## Workflow 2b: Download from Deezer

**Goal:** Download from Deezer with auto-registration.

```bash
# Via unified router (recommended)
tools/get "https://www.deezer.com/en/album/123456"

# Or direct wrapper
tools/deemix "https://www.deezer.com/en/track/789"
```

**Defaults:**
- Path: `~/Music/mdl/deezer`
- Bitrate: FLAC
- Auto-registers to DB with `--source deezer`

**Override path:**
```bash
tools/deemix --path /custom/path "https://www.deezer.com/album/123"
```

---

## Workflow 3: Complete Intake Pipeline

**Goal:** Full pipeline from download to final library.

```
intake → index → decide → execute → verify → report
```

### Step 1: Download (intake)

```bash
# Beatport
tools/get-sync "https://www.beatport.com/release/example/12345"

# Or Tidal
tools/get "https://tidal.com/browse/album/67890"
```

### Step 2: Register (index)

```bash
tagslut index register \
  --zone staging \
  --recursive \
  /path/to/downloads
```

### Step 3: Check for Issues (index)

```bash
# Duplicate check
tagslut index check \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# Duration check (DJ safety)
tagslut index duration-check \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

### Step 4: Generate Plan (decide)

```bash
tagslut decide plan \
  --profile default \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --output output/move_plan.json
```

### Step 5: Review Plan

```bash
tagslut report plan-summary \
  --plan output/move_plan.json
```

### Step 6: Execute Plan (execute)

```bash
tagslut execute move-plan \
  --plan output/move_plan.json
```

### Step 7: Verify (verify)

```bash
tagslut verify receipts \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

tagslut verify duration \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

### Step 8: Generate Report (report)

```bash
tagslut report duration \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --output artifacts/duration_report.md
```

---

## Workflow 4: OneTagger ISRC Enrichment

**Goal:** Add ISRC tags to FLAC files missing them.

### Step 1: Build M3U of Files Missing ISRC

```bash
tools/tag-build \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --output output/onetagger_batch.m3u
```

### Step 2: Run OneTagger

```bash
tools/tag-run \
  --m3u output/onetagger_batch.m3u
```

### Step 3: Update Database with New Tags

```bash
tagslut index enrich \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

---

## Workflow 5: Direct Promotion by Tags

**Goal:** Move files from staging to library using tag-based destination rules.

```bash
python tools/review/promote_by_tags.py \
  --source /path/to/staging \
  --dest /path/to/library \
  --move-log artifacts/moves_$(date +%Y%m%d_%H%M%S).jsonl \
  --dry-run  # Remove for actual execution
```

**Important:** Always run with `--dry-run` first to preview moves.

---

## Workflow 6: Quarantine Problematic Files

**Goal:** Move problematic files to quarantine for manual review.

### Step 1: Generate Quarantine Plan

```bash
tagslut decide plan \
  --profile quarantine \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --output output/quarantine_plan.json
```

### Step 2: Review Plan

```bash
tagslut report plan-summary \
  --plan output/quarantine_plan.json
```

### Step 3: Execute Quarantine

```bash
tagslut execute quarantine-plan \
  --plan output/quarantine_plan.json
```

---

## Workflow 7: Duration Reference Update

**Goal:** Update reference durations for DJ safety checks.

### Step 1: Set Reference Durations

```bash
tagslut index set-duration-ref \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --source beatport  # or tidal
```

### Step 2: Verify Duration Consistency

```bash
tagslut index duration-audit \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

---

## Workflow 8: Recovery and Repair

**Goal:** Recover from interrupted operations or repair issues.

### Step 1: Check Recovery Status

```bash
tagslut verify recovery \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

### Step 2: Generate Recovery Report

```bash
tagslut report recovery \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --output artifacts/recovery_report.md
```

### Step 3: Review and Act

See `docs/PROVENANCE_AND_RECOVERY.md` for detailed recovery procedures.

---

## Source Registration Matrix

| Source | Wrapper | --source Flag | Auto-register | Default Path |
|--------|---------|---------------|---------------|--------------|
| Beatport | `tools/get`, `tools/get-sync` | `bpdl` | No | config-defined |
| Tidal | `tools/get`, `tools/tiddl` | `tidal` | No | `~/Downloads/tiddl/` |
| Deezer | `tools/get`, `tools/deemix` | `deezer` | **Yes** | `~/Music/mdl/deezer` |
| Qobuz | N/A | N/A | N/A | **Not in active workflows** |

### Manual Registration Commands

```bash
# Beatport downloads
tagslut index register /path/to/bpdl/downloads --source bpdl --execute

# Tidal downloads
tagslut index register ~/Downloads/tiddl/ --source tidal --execute

# Deezer (auto-registered, but if needed)
tagslut index register ~/Music/mdl/deezer --source deezer --execute
```

---

## Match Strategy Reference

The pre-download check tool uses this matching hierarchy:

1. **ISRC** (highest confidence) - Exact ISRC match
2. **Beatport Track ID** - Exact Beatport ID match (Beatport links only)
3. **Title + Artist + Album** - Normalized exact match
4. **Title + Artist** - Normalized exact match (fallback)

Tracks that match any of these are marked `skip`. Tracks that don't match are marked `keep` and their URLs are written to the keep file for downloading.
