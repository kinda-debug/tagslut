# Workflows

# Workflows

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
  /path/to/downloaded/files \
  --source bpdl \
  --execute
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
  /path/to/downloads \
  --source bpdl \
  --execute
```

### Step 3: Check for Issues (index)

```bash
# Duplicate check
tagslut index check \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# Duration check (DJ safety)
tagslut index duration-check \
  /path/to/downloads \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

### Step 4: Generate Plan (decide)

```bash
tagslut decide plan \
  --policy library_balanced \
  --input output/candidates.json \
  --output output/move_plan.json
```

### Step 5: Review Plan

```bash
tagslut report plan-summary output/move_plan.json
```

### Step 6: Execute Plan (execute)

```bash
tagslut execute move-plan \
  output/move_plan.csv \
  --source-root /path/to/downloads \
  --dest-root /path/to/library \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --execute
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
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
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
  --policy quarantine \
  --input output/quarantine_candidates.json \
  --output output/quarantine_plan.json
```

### Step 2: Review Plan

```bash
tagslut report plan-summary output/quarantine_plan.json
```

### Step 3: Execute Quarantine

```bash
tagslut execute quarantine-plan \
  output/quarantine_plan.csv \
  --library-root /path/to/library \
  --quarantine-root /path/to/quarantine \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --execute
```

---

## Workflow 7: Duration Reference Update

**Goal:** Update reference durations for DJ safety checks.

### Step 1: Set Reference Durations

```bash
tagslut index set-duration-ref \
  /path/to/known-good.flac \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --confirm \
  --execute
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

## Workflow 9: Genre Normalization

**Goal:** Normalize genre/style metadata across files and optionally backfill the database with canonical genre values.

**Context:** Genre tags vary widely in format and hierarchy. This workflow uses centralized normalization rules to standardize them across your library, supporting both Beatport-style hierarchies and custom mappings.

### Option A: DB Backfill (Canonical Values)

Normalize genre/style tags across a path and update database `canonical_genre` and `canonical_sub_genre` fields.

```bash
# Dry-run: report what would be normalized
python tools/review/normalize_genres.py \
  /Volumes/DJSSD/LIBRARY \
  --db "$TAGSLUT_DB" \
  --rules tools/rules/genre_normalization.json \
  --output artifacts/genre_normalization_report.md \
  --csv artifacts/genre_normalization_rows.csv

# Execute: write to database
python tools/review/normalize_genres.py \
  /Volumes/DJSSD/LIBRARY \
  --db "$TAGSLUT_DB" \
  --rules tools/rules/genre_normalization.json \
  --output artifacts/genre_normalization_report.md \
  --csv artifacts/genre_normalization_rows.csv \
  --execute
```

**Output:**
- `genre_normalization_report.md` — Summary of scan and updates
- `genre_normalization_rows.csv` — Detailed row-by-row mapping (original → normalized)

### Option B: In-Place Tag Normalization

Apply normalized genre tags directly to FLAC files without touching the database.

```bash
# Dry-run: scan and report
python tools/review/tag_normalized_genres.py \
  /Volumes/DJSSD/LIBRARY \
  --rules tools/rules/genre_normalization.json \
  --limit 100

# Execute: write tags to files
python tools/review/tag_normalized_genres.py \
  /Volumes/DJSSD/LIBRARY \
  --rules tools/rules/genre_normalization.json \
  --execute
```

**Tag Output (Beatport-compatible):**
- `GENRE` — Primary genre (e.g., "House")
- `SUBGENRE` — Style/sub-genre (e.g., "Deep House")
- `GENRE_PREFERRED` — Preferred for cascading (style if present, else genre)
- `GENRE_FULL` — Hierarchical format (e.g., "House | Deep House")

### Option C: Combined Workflow (DB + Tags)

Both backfill the database AND apply tags in-place:

```bash
# Step 1: Backfill DB with canonical values
python tools/review/normalize_genres.py \
  /Volumes/DJSSD/LIBRARY \
  --db "$TAGSLUT_DB" \
  --rules tools/rules/genre_normalization.json \
  --execute

# Step 2: Apply tags to files for portability
python tools/review/tag_normalized_genres.py \
  /Volumes/DJSSD/LIBRARY \
  --rules tools/rules/genre_normalization.json \
  --execute
```

### Normalization Rules Format

Create or edit `tools/rules/genre_normalization.json`:

```json
{
  "genre_map": {
    "House Music": "House",
    "Tech House": "Tech House",
    "Deep House": "House",
    "UK Garage": "UK Garage / Bassline"
  },
  "style_map": {
    "Deep House": "Deep House",
    "Soulful House": "Soulful",
    "Minimal": "Minimal / Deep Tech",
    "Liquid": "Liquid"
  }
}
```

**Reference:** See `docs/archive/inactive-root-docs-2026-02-09/Beatport Genres and Sub-Genres.md` for complete Beatport taxonomy.

### Implementation Notes

- Both scripts use shared `GenreNormalizer` class (`tagslut/metadata/genre_normalization.py`) for consistent logic
- Cascade priority: `GENRE_PREFERRED` → `SUBGENRE` → `GENRE` → `GENRE_FULL` → fallback to first available
- "Dropped tags" are reported in CSV for audit (tags that were present but not used)
- Safe by default: dry-run is always the first step; use `--execute` to write changes

---

## Match Strategy Reference

The pre-download check tool uses this matching hierarchy:

1. **ISRC** (highest confidence) - Exact ISRC match
2. **Beatport Track ID** - Exact Beatport ID match (Beatport links only)
3. **Title + Artist + Album** - Normalized exact match
4. **Title + Artist** - Normalized exact match (fallback)

Tracks that match any of these are marked `skip`. Tracks that don't match are marked `keep` and their URLs are written to the keep file for downloading.

## Custom Workflow (Full Commands + Variables)

# Custom Workflow (Full Commands + Variables)

This is your end-to-end operating runbook for intake, metadata, health checks, promotion, and playlist export.

## 0) Variables

Set these once per shell session.

```bash
# Core paths
export REPO_ROOT="/path/to/your/tagslut"
export TAGSLUT_DB="/path/to/your/tagslut_db/EPOCH_PLACEHOLDER/music.db"
export LIBRARY_ROOT="/Volumes/MUSIC/LIBRARY"
export STAGING_ROOT="$HOME/Music/mdl"

# Output/log roots
export OUT_DIR="$REPO_ROOT/output"
export ARTIFACTS_DIR="$REPO_ROOT/artifacts"

# Optional provider/auth config
export TAGSLUT_ARTIFACTS="$ARTIFACTS_DIR"
export TAGSLUT_ZONES="$REPO_ROOT/config/zones.yaml"

# Policy choices
export PROVIDERS="beatport,tidal"
export NO_QOBUZ="1"
```

## 1) Environment Check

```bash
cd "$REPO_ROOT"
poetry --version
poetry run python --version
```

## 2) Pre-Download DB Check (Skip What You Already Have)

### 2.1 Single URL

```bash
python tools/review/pre_download_check.py \
  --input <(printf '%s\n' "https://tidal.com/album/447061568/u") \
  --db "$TAGSLUT_DB" \
  --out-dir "$OUT_DIR/precheck"
```

### 2.2 Links file

```bash
python tools/review/pre_download_check.py \
  --input ~/links.txt \
  --db "$TAGSLUT_DB" \
  --out-dir "$OUT_DIR/precheck"
```

### 2.3 Automatic keep-only download

```bash
tools/get-auto --links-file ~/links.txt
```

## 3) Downloaders (Source-Aware)

### 3.1 Unified router

```bash
tools/get "https://www.beatport.com/release/.../..."
tools/get "https://tidal.com/browse/album/..."
tools/get "https://www.deezer.com/en/track/..."
```

### 3.2 Direct wrappers

```bash
# Beatport
tools/get-sync "https://www.beatport.com/release/.../..."

# Tidal
tools/tiddl "https://tidal.com/browse/album/..."

# Deezer (FLAC by default, auto-register source=deezer)
tools/deemix "https://www.deezer.com/en/track/..."
```

## 4) Register New Audio Into DB

```bash
poetry run tagslut index register \
  "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" \
  --source staging \
  --execute
```

If source-specific folder:

```bash
poetry run tagslut index register "$STAGING_ROOT/deezer" --db "$TAGSLUT_DB" --source deezer --execute
poetry run tagslut index register "$STAGING_ROOT/tiddl" --db "$TAGSLUT_DB" --source tidal --execute
poetry run tagslut index register "$STAGING_ROOT/beatport" --db "$TAGSLUT_DB" --source beatport --execute
```

## 5) Enrich Metadata (Beatport + Tidal)

```bash
poetry run tagslut index enrich \
  --db "$TAGSLUT_DB" \
  --providers "$PROVIDERS" \
  --path "$STAGING_ROOT/%" \
  --retry-no-match \
  --execute
```

Notes:
- Keep Qobuz out by not including it in `--providers`.
- Use `--force` only when you intentionally want full re-enrichment.

## 6) Duration Health + Verification

### 6.1 Measure and classify

```bash
poetry run tagslut index duration-check \
  "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" \
  --execute \
  --dj-only
```

### 6.2 Verify status buckets

```bash
poetry run tagslut verify duration \
  --db "$TAGSLUT_DB" \
  --dj-only \
  --status ok,warn,fail,unknown
```

## 7) Promote to Library (Move Workflow)

### 7.1 Dry run

```bash
poetry run tagslut execute promote-tags \
  "$STAGING_ROOT" \
  --dest "$LIBRARY_ROOT"
```

### 7.2 Execute

```bash
poetry run tagslut execute promote-tags \
  "$STAGING_ROOT" \
  --dest "$LIBRARY_ROOT" \
  --execute
```

## 8) Roon M3U Export

```bash
poetry run tagslut report m3u "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --source library \
  --m3u-dir "$LIBRARY_ROOT" \
  --merge
```

Duration status buckets:

```bash
poetry run tagslut verify duration --db "$TAGSLUT_DB" --status warn,fail,unknown
poetry run tagslut report duration --db "$TAGSLUT_DB"
```

## 9) Rekordbox MP3 320 (from playlist)

```bash
export SRC_M3U="$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES.m3u"
export MP3_OUT="$HOME/Music/Rekordbox_MP3_320"

python scripts/convert_m3u_to_mp3_320.py \
  --input-m3u "$SRC_M3U" \
  --output-root "$MP3_OUT" \
  --dedupe \
  --embed-cover
```

## 10) Dropbox Intake Cleanup (Optional)

```bash
export DROPBOX_SYNC_ROOT="/Volumes/bad/dbx/Dropbox"

# Scan/verify fully downloaded FLACs
python scripts/scan_dropbox_audio_health.py --root "$DROPBOX_SYNC_ROOT"

# Promote valid files
poetry run tagslut execute promote-tags \
  --db "$TAGSLUT_DB" \
  --source "$DROPBOX_SYNC_ROOT/Music Hi-Res" \
  --dest "$LIBRARY_ROOT" \
  --execute
```

## 11) Daily Operator Sequence

```bash
# 1) precheck links
# 2) download keep-only
# 3) register
# 4) enrich beatport+tidal
# 5) duration-check
# 6) promote
# 7) export m3u buckets
```

## 12) Quick Troubleshooting

```bash
# Check auth
poetry run tagslut auth status

# Show command groups
poetry run tagslut --help

# Check DB file exists
ls -lh "$TAGSLUT_DB"

# Check latest precheck output
ls -lt "$OUT_DIR/precheck" | head
```

## 13) What This Workflow Enforces

- No Qobuz in active enrichment.
- Beatport + Tidal priority for metadata references.
- Duration-based DJ safety gates (`ok/warn/fail/unknown`).
- Roon playlists exported directly to library root.
- Source-aware registration for provenance and recovery.

## 14) Unknown Reduction (Head-On, No Qobuz)

Use this when `duration_status=unknown` is too high.

```bash
# 1) Local bootstrap of refs (no provider tokens)
python scripts/bootstrap_duration_refs_local.py \
  --db "$TAGSLUT_DB" \
  --execute

# 2) Recompute durations for library
poetry run tagslut index duration-check \
  "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --execute \
  --dj-only

# 3) Optional provider pass (Beatport + Tidal only)
poetry run tagslut index enrich \
  --db "$TAGSLUT_DB" \
  --providers beatport,tidal \
  --path "$LIBRARY_ROOT/%" \
  --recovery \
  --retry-no-match \
  --execute

# 4) Verify status counts
poetry run tagslut verify duration \
  --db "$TAGSLUT_DB" \
  --dj-only \
  --status ok,warn,fail,unknown
```

## 15) False Fail Reassessment (Extended/Remix Mismatch)

Use this for "audio is fine but marked fail" cases.

```bash
python scripts/reassess_duration_variant_mismatch.py \
  --db "$TAGSLUT_DB" \
  --execute
```

Then refresh playlists:

```bash
poetry run tagslut report m3u "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --source library \
  --m3u-dir "$LIBRARY_ROOT" \
  --merge
```

## 16) Playlist Audit Against DB (XLSX)

```bash
# Example playlist audit script
python scripts/audit_playlist_xlsx.py \
  --xlsx "$HOME/Desktop/DJ_NEW.xlsx" \
  --db "$TAGSLUT_DB" \
  --library-root "$LIBRARY_ROOT"
```

Expected outputs:
- status report CSV/XLSX
- `*_ok.m3u`, `*_warn.m3u`, `*_fail.m3u`, `*_unknown.m3u`

## 17) Rekordbox Conversion (Whole Playlist, Deduped, 320 CBR)

```bash
export SRC_M3U="$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES.m3u"
export OUT_MP3="$HOME/Music/Rekordbox_MP3_320"

python scripts/convert_m3u_to_mp3_320.py \
  --input-m3u "$SRC_M3U" \
  --output-root "$OUT_MP3" \
  --dedupe \
  --bitrate 320 \
  --cbr
```

Cover embed pass (if source contains art):

```bash
python scripts/embed_artwork_from_sources.py \
  --source-m3u "$SRC_M3U" \
  --target-m3u "$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES_FULL_MP3_320.m3u"
```

## 18) Relink After Picard Renames (Lightweight New DB Flow)

```bash
export RELINK_DB="/path/to/your/tagslut_db/EPOCH_2026-02-10_RELINK/music.db"

python scripts/bootstrap_relink_db.py \
  --from-db "/path/to/your/tagslut_db/EPOCH_2026-02-08/music.db" \
  --to-db "$RELINK_DB"

poetry run tagslut index register \
  "$LIBRARY_ROOT" \
  --db "$RELINK_DB" \
  --source relink \
  --execute
```

## 19) Dropbox Promotion + Cloud Deletion Safety

```bash
export DBX_LOCAL="/Volumes/bad/dbx/Dropbox"
export DBX_TOKEN_FILE="$HOME/dbtoken.txt"

# 1) Verify local files are fully downloaded / decodable
python scripts/scan_dropbox_audio_health.py --root "$DBX_LOCAL"

# 2) Promote valid FLACs
poetry run tagslut execute promote-tags \
  "$DBX_LOCAL/Music Hi-Res" \
  --dest "$LIBRARY_ROOT" \
  --execute

# 3) Delete in cloud only with valid write-scope token
# Required Dropbox scopes: files.content.write + files.metadata.read
python scripts/delete_dropbox_cloud_paths.py \
  --token-file "$DBX_TOKEN_FILE" \
  --paths-file "$REPO_ROOT/dropbox_processed_cloud_paths.txt"
```

If cloud delete returns `missing_scope` or `expired_access_token`, regenerate token and retry.

## 20) Daily “No-Pollution” Policy

- Always precheck links against DB before download.
- Never promote without duration-check.
- Keep providers restricted to `beatport,tidal` unless explicitly needed.
- Treat `warn/fail` as review queues, not auto-delete signals.
- Rebuild Roon playlists from DB statuses after each major run.

## Health Rescan Workflow (Trusted First, DJ Next)

# Health Rescan Workflow (Trusted First, DJ Next)

This workflow rescans files in DB order of trust priority without moving anything.

Priority order:
1. `accepted`
2. `staging`
3. `suspect` DJ-like first (`is_dj_material=1` or DJ/electronic genre hints)
4. remaining `suspect`
5. `archive`
6. `quarantine`/other

Health rule:
- Only tracks with `flac_ok=1` and `integrity_state='valid'` are included in output playlist.

Electronic-only rule:
- Add `--electronic-only` to exclude non-electronic tracks from both scan queue and playlist output.

Metadata hoarding:
- Add `--hoard-metadata` to hoard embedded tags from healthy files into `files.metadata_json`.

## Execute

### Option A: Current relink DB
```bash
scripts/workflow_health_rescan.py \
  --db /Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --root /Volumes/MUSIC \
  --workers 8 \
  --electronic-only \
  --hoard-metadata \
  --playlist-out /Volumes/MUSIC/LIBRARY/HEALTHY_PRIORITY_WORKFLOW.m3u
```

### Option B: Larger accepted snapshot DB
```bash
scripts/workflow_health_rescan.py \
  --db /Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-08/music.db \
  --root /Volumes/MUSIC \
  --workers 8 \
  --electronic-only \
  --hoard-metadata \
  --playlist-out /Volumes/MUSIC/LIBRARY/HEALTHY_PRIORITY_WORKFLOW.m3u
```

## Optional

Dry run (no DB writes):
```bash
scripts/workflow_health_rescan.py --db /path/to/music.db --dry-run --limit 500
```

Skip playlist generation:
```bash
scripts/workflow_health_rescan.py --db /path/to/music.db --no-playlist
```

## Outputs

- JSONL per-track scan log: `artifacts/logs/health_rescan_*.jsonl`
- Summary JSON: `artifacts/logs/health_rescan_*_summary.json`
- Playlist (health-pass only): `/Volumes/MUSIC/LIBRARY/HEALTHY_PRIORITY_WORKFLOW.m3u`

## Offline Workflow Cheat Sheet (FLAC → MP3 → Lexicon → Rekordbox)

# Offline Workflow Cheat Sheet (FLAC → MP3 → Lexicon → Rekordbox)

This is the exact, minimal workflow you can run while offline. Items that require internet are clearly marked.

Paths used
- FLAC master: `/Volumes/MUSIC/LIBRARY`
- Staging downloads: `/Users/georgeskhawam/Music/tiddl`
- DJ MP3 library (USB): `/Volumes/DJSSD/DJ_LIBRARY_MP3`
- Tagslut DB: `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db`
- Tagslut repo: `/Users/georgeskhawam/Projects/tagslut`

## A) ONLINE STEPS (do these before going offline)

### Quick interactive pipeline (recommended)
If you want a single command that prompts for the root folder and runs the full pipeline:
```bash
cd /Users/georgeskhawam/Projects/tagslut
export PYTHONPATH=.
tools/review/process_root.py
```

Notes:
- It **auto‑sets trust** (pre/post = 3) and will not prompt.
- It runs integrity with `--execute` so `flac_ok` is written.
- It runs hoarding enrichment, genre normalization, tag writes, art embedding, and promote/replace.

1) Download from Tidal (online)
```bash
TIDDL_BIN=/Users/georgeskhawam/.local/pipx/venvs/tiddl/bin/tiddl \
/Users/georgeskhawam/Projects/tagslut/tools/tiddl download \
  --path /Users/georgeskhawam/Music/tiddl \
  --scan-path /Users/georgeskhawam/Music/tiddl \
  url https://tidal.com/album/XXXX/u
```

2) Register into DB (can be offline, but usually run immediately after download)
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 -m tagslut index register /Users/georgeskhawam/Music/tiddl \
  --source tidal \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --dj-only --no-prompt --execute
```

3) Enrich metadata from providers (online)
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 -m tagslut index enrich \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --hoarding \
  --providers beatport,deezer,apple_music,itunes \
  --path '/Users/georgeskhawam/Music/tiddl/%' \
  --zones staging \
  --execute
```

## B) OFFLINE STEPS (safe without internet)

4) Integrity check (writes `flac_ok`)
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 tools/review/check_integrity_update_db.py /Users/georgeskhawam/Music/tiddl \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --execute
```

5) Normalize genres (DB backfill)
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 tools/review/normalize_genres.py /Users/georgeskhawam/Music/tiddl \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --rules tools/rules/genre_normalization.json \
  --execute
```

6) Write normalized genre tags into FLAC files
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 tools/review/tag_normalized_genres.py /Users/georgeskhawam/Music/tiddl \
  --rules tools/rules/genre_normalization.json \
  --execute
```

7) Promote FLAC to master library (replace+merge)
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 tools/review/promote_replace_merge.py /Users/georgeskhawam/Music/tiddl \
  --dest /Volumes/MUSIC/LIBRARY \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --execute
```

8) Transcode **new tracks only** (from `MDL_NEW_TRACKS.m3u`) to DJSSD
```bash
python3 - <<'PY'
import os, subprocess
from pathlib import Path

SRC_ROOT = Path('/Volumes/MUSIC/LIBRARY')
DST_ROOT = Path('/Volumes/DJSSD/DJ_LIBRARY_MP3')
M3U = Path('/Volumes/MUSIC/LIBRARY/MDL_NEW_TRACKS.m3u')

lines = [l.strip() for l in M3U.read_text(encoding='utf-8', errors='replace').splitlines()]
paths = []
seen = set()
for l in lines:
    if not l or l.startswith('#'):
        continue
    p = Path(l)
    if p in seen:
        continue
    seen.add(p)
    paths.append(p)

for src in paths:
    if not src.exists():
        continue
    try:
        rel = src.relative_to(SRC_ROOT)
    except Exception:
        continue
    out = (DST_ROOT / rel).with_suffix('.mp3')
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        continue

    tmp = out.with_suffix('.tmp.mp3')
    cmd = [
        'ffmpeg','-hide_banner','-loglevel','error','-stats','-y',
        '-i', str(src),
        '-map','0:a','-map','0:v?','-map_metadata','0',
        '-c:a','libmp3lame','-b:a','320k','-minrate','320k','-maxrate','320k','-bufsize','320k',
        '-id3v2_version','3','-write_id3v1','1',
        '-c:v','copy','-disposition:v','attached_pic',
        str(tmp)
    ]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        if tmp.exists():
            tmp.unlink()
        continue
    os.replace(tmp, out)
PY
```

9) Update MP3 playlists (mirror the kept M3U names)
Use this pattern when you’re ready to mirror the FLAC playlists on DJSSD:
```bash
# Example: mirror DJ_SET_POOL_4TO12.m3u to DJSSD paths
python3 - <<'PY'
from pathlib import Path

src_m3u = Path('/Volumes/MUSIC/LIBRARY/DJ_SET_POOL_4TO12.m3u')
dst_m3u = Path('/Volumes/DJSSD/DJ_SET_POOL_4TO12.m3u')

src_root = '/Volumes/MUSIC/LIBRARY/'
dst_root = '/Volumes/DJSSD/DJ_LIBRARY_MP3/'

lines = [l.strip() for l in src_m3u.read_text(encoding='utf-8', errors='replace').splitlines()]
paths = [l for l in lines if l and not l.startswith('#')]

mapped = [p.replace(src_root, dst_root).rsplit('.',1)[0] + '.mp3' for p in paths]
dst_m3u.write_text('\n'.join(mapped) + ('\n' if mapped else ''), encoding='utf-8')
PY
```

## C) LEXICON + REKORDBOX (offline)

10) Lexicon import
- Import folder: `/Volumes/DJSSD/DJ_LIBRARY_MP3`

11) Rekordbox import + analysis
- Import MP3 library root
- Analyze BPM/beatgrid/phrase
- Disable **Preferences → Advanced → Write tags to file**

12) Export to USB
- Rekordbox Export Mode → export to `/Volumes/DJSSD`

---

## Notes
- **Genre/BPM/Key** are written into the DB during enrichment; tags are only written into files by steps 5–6.
- Transcode step preserves artwork and uses ID3v2.3 (best Rekordbox compatibility).
- If you go fully offline, just skip Step A3 (enrich) until you’re back online.

## Advanced Procedures

# Custom Workflow (Full Commands + Variables)

This is your end-to-end operating runbook for intake, metadata, health checks, promotion, and playlist export.

## 0) Variables

Set these once per shell session.

```bash
# Core paths
export REPO_ROOT="/path/to/your/tagslut"
export TAGSLUT_DB="/path/to/your/tagslut_db/EPOCH_PLACEHOLDER/music.db"
export LIBRARY_ROOT="/Volumes/MUSIC/LIBRARY"
export STAGING_ROOT="$HOME/Music/mdl"

# Output/log roots
export OUT_DIR="$REPO_ROOT/output"
export ARTIFACTS_DIR="$REPO_ROOT/artifacts"

# Optional provider/auth config
export TAGSLUT_ARTIFACTS="$ARTIFACTS_DIR"
export TAGSLUT_ZONES="$REPO_ROOT/config/zones.yaml"

# Policy choices
export PROVIDERS="beatport,tidal"
export NO_QOBUZ="1"
```

## 1) Environment Check

```bash
cd "$REPO_ROOT"
poetry --version
poetry run python --version
```

## 2) Pre-Download DB Check (Skip What You Already Have)

### 2.1 Single URL

```bash
python tools/review/pre_download_check.py \
  --input <(printf '%s\n' "https://tidal.com/album/447061568/u") \
  --db "$TAGSLUT_DB" \
  --out-dir "$OUT_DIR/precheck"
```

### 2.2 Links file

```bash
python tools/review/pre_download_check.py \
  --input ~/links.txt \
  --db "$TAGSLUT_DB" \
  --out-dir "$OUT_DIR/precheck"
```

### 2.3 Automatic keep-only download

```bash
tools/get-auto --links-file ~/links.txt
```

## 3) Downloaders (Source-Aware)

### 3.1 Unified router

```bash
tools/get "https://www.beatport.com/release/.../..."
tools/get "https://tidal.com/browse/album/..."
tools/get "https://www.deezer.com/en/track/..."
```

### 3.2 Direct wrappers

```bash
# Beatport
tools/get-sync "https://www.beatport.com/release/.../..."

# Tidal
tools/tiddl "https://tidal.com/browse/album/..."

# Deezer (FLAC by default, auto-register source=deezer)
tools/deemix "https://www.deezer.com/en/track/..."
```

## 4) Register New Audio Into DB

```bash
poetry run tagslut index register \
  "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" \
  --source staging \
  --execute
```

If source-specific folder:

```bash
poetry run tagslut index register "$STAGING_ROOT/deezer" --db "$TAGSLUT_DB" --source deezer --execute
poetry run tagslut index register "$STAGING_ROOT/tiddl" --db "$TAGSLUT_DB" --source tidal --execute
poetry run tagslut index register "$STAGING_ROOT/beatport" --db "$TAGSLUT_DB" --source beatport --execute
```

## 5) Enrich Metadata (Beatport + Tidal)

```bash
poetry run tagslut index enrich \
  --db "$TAGSLUT_DB" \
  --providers "$PROVIDERS" \
  --path "$STAGING_ROOT/%" \
  --retry-no-match \
  --execute
```

Notes:
- Keep Qobuz out by not including it in `--providers`.
- Use `--force` only when you intentionally want full re-enrichment.

## 6) Duration Health + Verification

### 6.1 Measure and classify

```bash
poetry run tagslut index duration-check \
  "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" \
  --execute \
  --dj-only
```

### 6.2 Verify status buckets

```bash
poetry run tagslut verify duration \
  --db "$TAGSLUT_DB" \
  --dj-only \
  --status ok,warn,fail,unknown
```

## 7) Promote to Library (Move Workflow)

### 7.1 Dry run

```bash
poetry run tagslut execute promote-tags \
  "$STAGING_ROOT" \
  --dest "$LIBRARY_ROOT"
```

### 7.2 Execute

```bash
poetry run tagslut execute promote-tags \
  "$STAGING_ROOT" \
  --dest "$LIBRARY_ROOT" \
  --execute
```

## 8) Roon M3U Export

```bash
poetry run tagslut report m3u "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --source library \
  --m3u-dir "$LIBRARY_ROOT" \
  --merge
```

Duration status buckets:

```bash
poetry run tagslut verify duration --db "$TAGSLUT_DB" --status warn,fail,unknown
poetry run tagslut report duration --db "$TAGSLUT_DB"
```

## 9) Rekordbox MP3 320 (from playlist)

```bash
export SRC_M3U="$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES.m3u"
export MP3_OUT="$HOME/Music/Rekordbox_MP3_320"

python scripts/convert_m3u_to_mp3_320.py \
  --input-m3u "$SRC_M3U" \
  --output-root "$MP3_OUT" \
  --dedupe \
  --embed-cover
```

## 10) Dropbox Intake Cleanup (Optional)

```bash
export DROPBOX_SYNC_ROOT="/Volumes/bad/dbx/Dropbox"

# Scan/verify fully downloaded FLACs
python scripts/scan_dropbox_audio_health.py --root "$DROPBOX_SYNC_ROOT"

# Promote valid files
poetry run tagslut execute promote-tags \
  --db "$TAGSLUT_DB" \
  --source "$DROPBOX_SYNC_ROOT/Music Hi-Res" \
  --dest "$LIBRARY_ROOT" \
  --execute
```

## 11) Daily Operator Sequence

```bash
# 1) precheck links
# 2) download keep-only
# 3) register
# 4) enrich beatport+tidal
# 5) duration-check
# 6) promote
# 7) export m3u buckets
```

## 12) Quick Troubleshooting

```bash
# Check auth
poetry run tagslut auth status

# Show command groups
poetry run tagslut --help

# Check DB file exists
ls -lh "$TAGSLUT_DB"

# Check latest precheck output
ls -lt "$OUT_DIR/precheck" | head
```

## 13) What This Workflow Enforces

- No Qobuz in active enrichment.
- Beatport + Tidal priority for metadata references.
- Duration-based DJ safety gates (`ok/warn/fail/unknown`).
- Roon playlists exported directly to library root.
- Source-aware registration for provenance and recovery.

## 14) Unknown Reduction (Head-On, No Qobuz)

Use this when `duration_status=unknown` is too high.

```bash
# 1) Local bootstrap of refs (no provider tokens)
python scripts/bootstrap_duration_refs_local.py \
  --db "$TAGSLUT_DB" \
  --execute

# 2) Recompute durations for library
poetry run tagslut index duration-check \
  "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --execute \
  --dj-only

# 3) Optional provider pass (Beatport + Tidal only)
poetry run tagslut index enrich \
  --db "$TAGSLUT_DB" \
  --providers beatport,tidal \
  --path "$LIBRARY_ROOT/%" \
  --recovery \
  --retry-no-match \
  --execute

# 4) Verify status counts
poetry run tagslut verify duration \
  --db "$TAGSLUT_DB" \
  --dj-only \
  --status ok,warn,fail,unknown
```

## 15) False Fail Reassessment (Extended/Remix Mismatch)

Use this for "audio is fine but marked fail" cases.

```bash
python scripts/reassess_duration_variant_mismatch.py \
  --db "$TAGSLUT_DB" \
  --execute
```

Then refresh playlists:

```bash
poetry run tagslut report m3u "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --source library \
  --m3u-dir "$LIBRARY_ROOT" \
  --merge
```

## 16) Playlist Audit Against DB (XLSX)

```bash
# Example playlist audit script
python scripts/audit_playlist_xlsx.py \
  --xlsx "$HOME/Desktop/DJ_NEW.xlsx" \
  --db "$TAGSLUT_DB" \
  --library-root "$LIBRARY_ROOT"
```

Expected outputs:
- status report CSV/XLSX
- `*_ok.m3u`, `*_warn.m3u`, `*_fail.m3u`, `*_unknown.m3u`

## 17) Rekordbox Conversion (Whole Playlist, Deduped, 320 CBR)

```bash
export SRC_M3U="$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES.m3u"
export OUT_MP3="$HOME/Music/Rekordbox_MP3_320"

python scripts/convert_m3u_to_mp3_320.py \
  --input-m3u "$SRC_M3U" \
  --output-root "$OUT_MP3" \
  --dedupe \
  --bitrate 320 \
  --cbr
```

Cover embed pass (if source contains art):

```bash
python scripts/embed_artwork_from_sources.py \
  --source-m3u "$SRC_M3U" \
  --target-m3u "$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES_FULL_MP3_320.m3u"
```

## 18) Relink After Picard Renames (Lightweight New DB Flow)

```bash
export RELINK_DB="/path/to/your/tagslut_db/EPOCH_2026-02-10_RELINK/music.db"

python scripts/bootstrap_relink_db.py \
  --from-db "/path/to/your/tagslut_db/EPOCH_2026-02-08/music.db" \
  --to-db "$RELINK_DB"

poetry run tagslut index register \
  "$LIBRARY_ROOT" \
  --db "$RELINK_DB" \
  --source relink \
  --execute
```

## 19) Dropbox Promotion + Cloud Deletion Safety

```bash
export DBX_LOCAL="/Volumes/bad/dbx/Dropbox"
export DBX_TOKEN_FILE="$HOME/dbtoken.txt"

# 1) Verify local files are fully downloaded / decodable
python scripts/scan_dropbox_audio_health.py --root "$DBX_LOCAL"

# 2) Promote valid FLACs
poetry run tagslut execute promote-tags \
  "$DBX_LOCAL/Music Hi-Res" \
  --dest "$LIBRARY_ROOT" \
  --execute

# 3) Delete in cloud only with valid write-scope token
# Required Dropbox scopes: files.content.write + files.metadata.read
python scripts/delete_dropbox_cloud_paths.py \
  --token-file "$DBX_TOKEN_FILE" \
  --paths-file "$REPO_ROOT/dropbox_processed_cloud_paths.txt"
```

If cloud delete returns `missing_scope` or `expired_access_token`, regenerate token and retry.

## 20) Daily “No-Pollution” Policy

- Always precheck links against DB before download.
- Never promote without duration-check.
- Keep providers restricted to `beatport,tidal` unless explicitly needed.
- Treat `warn/fail` as review queues, not auto-delete signals.
- Rebuild Roon playlists from DB statuses after each major run.

## Custom Workflow (Full Commands + Variables)

# Custom Workflow (Full Commands + Variables)

This is your end-to-end operating runbook for intake, metadata, health checks, promotion, and playlist export.

## 0) Variables

Set these once per shell session.

```bash
# Core paths
export REPO_ROOT="/path/to/your/tagslut"
export TAGSLUT_DB="/path/to/your/tagslut_db/EPOCH_PLACEHOLDER/music.db"
export LIBRARY_ROOT="/Volumes/MUSIC/LIBRARY"
export STAGING_ROOT="$HOME/Music/mdl"

# Output/log roots
export OUT_DIR="$REPO_ROOT/output"
export ARTIFACTS_DIR="$REPO_ROOT/artifacts"

# Optional provider/auth config
export TAGSLUT_ARTIFACTS="$ARTIFACTS_DIR"
export TAGSLUT_ZONES="$REPO_ROOT/config/zones.yaml"

# Policy choices
export PROVIDERS="beatport,tidal"
export NO_QOBUZ="1"
```

## 1) Environment Check

```bash
cd "$REPO_ROOT"
poetry --version
poetry run python --version
```

## 2) Pre-Download DB Check (Skip What You Already Have)

### 2.1 Single URL

```bash
python tools/review/pre_download_check.py \
  --input <(printf '%s\n' "https://tidal.com/album/447061568/u") \
  --db "$TAGSLUT_DB" \
  --out-dir "$OUT_DIR/precheck"
```

### 2.2 Links file

```bash
python tools/review/pre_download_check.py \
  --input ~/links.txt \
  --db "$TAGSLUT_DB" \
  --out-dir "$OUT_DIR/precheck"
```

### 2.3 Automatic keep-only download

```bash
tools/get-auto --links-file ~/links.txt
```

## 3) Downloaders (Source-Aware)

### 3.1 Unified router

```bash
tools/get "https://www.beatport.com/release/.../..."
tools/get "https://tidal.com/browse/album/..."
tools/get "https://www.deezer.com/en/track/..."
```

### 3.2 Direct wrappers

```bash
# Beatport
tools/get-sync "https://www.beatport.com/release/.../..."

# Tidal
tools/tiddl "https://tidal.com/browse/album/..."

# Deezer (FLAC by default, auto-register source=deezer)
tools/deemix "https://www.deezer.com/en/track/..."
```

## 4) Register New Audio Into DB

```bash
poetry run tagslut index register \
  "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" \
  --source staging \
  --execute
```

If source-specific folder:

```bash
poetry run tagslut index register "$STAGING_ROOT/deezer" --db "$TAGSLUT_DB" --source deezer --execute
poetry run tagslut index register "$STAGING_ROOT/tiddl" --db "$TAGSLUT_DB" --source tidal --execute
poetry run tagslut index register "$STAGING_ROOT/beatport" --db "$TAGSLUT_DB" --source beatport --execute
```

## 5) Enrich Metadata (Beatport + Tidal)

```bash
poetry run tagslut index enrich \
  --db "$TAGSLUT_DB" \
  --providers "$PROVIDERS" \
  --path "$STAGING_ROOT/%" \
  --retry-no-match \
  --execute
```

Notes:
- Keep Qobuz out by not including it in `--providers`.
- Use `--force` only when you intentionally want full re-enrichment.

## 6) Duration Health + Verification

### 6.1 Measure and classify

```bash
poetry run tagslut index duration-check \
  "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" \
  --execute \
  --dj-only
```

### 6.2 Verify status buckets

```bash
poetry run tagslut verify duration \
  --db "$TAGSLUT_DB" \
  --dj-only \
  --status ok,warn,fail,unknown
```

## 7) Promote to Library (Move Workflow)

### 7.1 Dry run

```bash
poetry run tagslut execute promote-tags \
  "$STAGING_ROOT" \
  --dest "$LIBRARY_ROOT"
```

### 7.2 Execute

```bash
poetry run tagslut execute promote-tags \
  "$STAGING_ROOT" \
  --dest "$LIBRARY_ROOT" \
  --execute
```

## 8) Roon M3U Export

```bash
poetry run tagslut report m3u "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --source library \
  --m3u-dir "$LIBRARY_ROOT" \
  --merge
```

Duration status buckets:

```bash
poetry run tagslut verify duration --db "$TAGSLUT_DB" --status warn,fail,unknown
poetry run tagslut report duration --db "$TAGSLUT_DB"
```

## 9) Rekordbox MP3 320 (from playlist)

```bash
export SRC_M3U="$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES.m3u"
export MP3_OUT="$HOME/Music/Rekordbox_MP3_320"

python scripts/convert_m3u_to_mp3_320.py \
  --input-m3u "$SRC_M3U" \
  --output-root "$MP3_OUT" \
  --dedupe \
  --embed-cover
```

## 10) Dropbox Intake Cleanup (Optional)

```bash
export DROPBOX_SYNC_ROOT="/Volumes/bad/dbx/Dropbox"

# Scan/verify fully downloaded FLACs
python scripts/scan_dropbox_audio_health.py --root "$DROPBOX_SYNC_ROOT"

# Promote valid files
poetry run tagslut execute promote-tags \
  --db "$TAGSLUT_DB" \
  --source "$DROPBOX_SYNC_ROOT/Music Hi-Res" \
  --dest "$LIBRARY_ROOT" \
  --execute
```

## 11) Daily Operator Sequence

```bash
# 1) precheck links
# 2) download keep-only
# 3) register
# 4) enrich beatport+tidal
# 5) duration-check
# 6) promote
# 7) export m3u buckets
```

## 12) Quick Troubleshooting

```bash
# Check auth
poetry run tagslut auth status

# Show command groups
poetry run tagslut --help

# Check DB file exists
ls -lh "$TAGSLUT_DB"

# Check latest precheck output
ls -lt "$OUT_DIR/precheck" | head
```

## 13) What This Workflow Enforces

- No Qobuz in active enrichment.
- Beatport + Tidal priority for metadata references.
- Duration-based DJ safety gates (`ok/warn/fail/unknown`).
- Roon playlists exported directly to library root.
- Source-aware registration for provenance and recovery.

## 14) Unknown Reduction (Head-On, No Qobuz)

Use this when `duration_status=unknown` is too high.

```bash
# 1) Local bootstrap of refs (no provider tokens)
python scripts/bootstrap_duration_refs_local.py \
  --db "$TAGSLUT_DB" \
  --execute

# 2) Recompute durations for library
poetry run tagslut index duration-check \
  "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --execute \
  --dj-only

# 3) Optional provider pass (Beatport + Tidal only)
poetry run tagslut index enrich \
  --db "$TAGSLUT_DB" \
  --providers beatport,tidal \
  --path "$LIBRARY_ROOT/%" \
  --recovery \
  --retry-no-match \
  --execute

# 4) Verify status counts
poetry run tagslut verify duration \
  --db "$TAGSLUT_DB" \
  --dj-only \
  --status ok,warn,fail,unknown
```

## 15) False Fail Reassessment (Extended/Remix Mismatch)

Use this for "audio is fine but marked fail" cases.

```bash
python scripts/reassess_duration_variant_mismatch.py \
  --db "$TAGSLUT_DB" \
  --execute
```

Then refresh playlists:

```bash
poetry run tagslut report m3u "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --source library \
  --m3u-dir "$LIBRARY_ROOT" \
  --merge
```

## 16) Playlist Audit Against DB (XLSX)

```bash
# Example playlist audit script
python scripts/audit_playlist_xlsx.py \
  --xlsx "$HOME/Desktop/DJ_NEW.xlsx" \
  --db "$TAGSLUT_DB" \
  --library-root "$LIBRARY_ROOT"
```

Expected outputs:
- status report CSV/XLSX
- `*_ok.m3u`, `*_warn.m3u`, `*_fail.m3u`, `*_unknown.m3u`

## 17) Rekordbox Conversion (Whole Playlist, Deduped, 320 CBR)

```bash
export SRC_M3U="$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES.m3u"
export OUT_MP3="$HOME/Music/Rekordbox_MP3_320"

python scripts/convert_m3u_to_mp3_320.py \
  --input-m3u "$SRC_M3U" \
  --output-root "$OUT_MP3" \
  --dedupe \
  --bitrate 320 \
  --cbr
```

Cover embed pass (if source contains art):

```bash
python scripts/embed_artwork_from_sources.py \
  --source-m3u "$SRC_M3U" \
  --target-m3u "$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES_FULL_MP3_320.m3u"
```

## 18) Relink After Picard Renames (Lightweight New DB Flow)

```bash
export RELINK_DB="/path/to/your/tagslut_db/EPOCH_2026-02-10_RELINK/music.db"

python scripts/bootstrap_relink_db.py \
  --from-db "/path/to/your/tagslut_db/EPOCH_2026-02-08/music.db" \
  --to-db "$RELINK_DB"

poetry run tagslut index register \
  "$LIBRARY_ROOT" \
  --db "$RELINK_DB" \
  --source relink \
  --execute
```

## 19) Dropbox Promotion + Cloud Deletion Safety

```bash
export DBX_LOCAL="/Volumes/bad/dbx/Dropbox"
export DBX_TOKEN_FILE="$HOME/dbtoken.txt"

# 1) Verify local files are fully downloaded / decodable
python scripts/scan_dropbox_audio_health.py --root "$DBX_LOCAL"

# 2) Promote valid FLACs
poetry run tagslut execute promote-tags \
  "$DBX_LOCAL/Music Hi-Res" \
  --dest "$LIBRARY_ROOT" \
  --execute

# 3) Delete in cloud only with valid write-scope token
# Required Dropbox scopes: files.content.write + files.metadata.read
python scripts/delete_dropbox_cloud_paths.py \
  --token-file "$DBX_TOKEN_FILE" \
  --paths-file "$REPO_ROOT/dropbox_processed_cloud_paths.txt"
```

If cloud delete returns `missing_scope` or `expired_access_token`, regenerate token and retry.

## 20) Daily “No-Pollution” Policy

- Always precheck links against DB before download.
- Never promote without duration-check.
- Keep providers restricted to `beatport,tidal` unless explicitly needed.
- Treat `warn/fail` as review queues, not auto-delete signals.
- Rebuild Roon playlists from DB statuses after each major run.

## Health Rescan Workflow (Trusted First, DJ Next)

# Health Rescan Workflow (Trusted First, DJ Next)

This workflow rescans files in DB order of trust priority without moving anything.

Priority order:
1. `accepted`
2. `staging`
3. `suspect` DJ-like first (`is_dj_material=1` or DJ/electronic genre hints)
4. remaining `suspect`
5. `archive`
6. `quarantine`/other

Health rule:
- Only tracks with `flac_ok=1` and `integrity_state='valid'` are included in output playlist.

Electronic-only rule:
- Add `--electronic-only` to exclude non-electronic tracks from both scan queue and playlist output.

Metadata hoarding:
- Add `--hoard-metadata` to hoard embedded tags from healthy files into `files.metadata_json`.

## Execute

### Option A: Current relink DB
```bash
scripts/workflow_health_rescan.py \
  --db /Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --root /Volumes/MUSIC \
  --workers 8 \
  --electronic-only \
  --hoard-metadata \
  --playlist-out /Volumes/MUSIC/LIBRARY/HEALTHY_PRIORITY_WORKFLOW.m3u
```

### Option B: Larger accepted snapshot DB
```bash
scripts/workflow_health_rescan.py \
  --db /Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-08/music.db \
  --root /Volumes/MUSIC \
  --workers 8 \
  --electronic-only \
  --hoard-metadata \
  --playlist-out /Volumes/MUSIC/LIBRARY/HEALTHY_PRIORITY_WORKFLOW.m3u
```

## Optional

Dry run (no DB writes):
```bash
scripts/workflow_health_rescan.py --db /path/to/music.db --dry-run --limit 500
```

Skip playlist generation:
```bash
scripts/workflow_health_rescan.py --db /path/to/music.db --no-playlist
```

## Outputs

- JSONL per-track scan log: `artifacts/logs/health_rescan_*.jsonl`
- Summary JSON: `artifacts/logs/health_rescan_*_summary.json`
- Playlist (health-pass only): `/Volumes/MUSIC/LIBRARY/HEALTHY_PRIORITY_WORKFLOW.m3u`

## Offline Workflow Cheat Sheet (FLAC → MP3 → Lexicon → Rekordbox)

# Offline Workflow Cheat Sheet (FLAC → MP3 → Lexicon → Rekordbox)

This is the exact, minimal workflow you can run while offline. Items that require internet are clearly marked.

Paths used
- FLAC master: `/Volumes/MUSIC/LIBRARY`
- Staging downloads: `/Users/georgeskhawam/Music/tiddl`
- DJ MP3 library (USB): `/Volumes/DJSSD/DJ_LIBRARY_MP3`
- Tagslut DB: `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db`
- Tagslut repo: `/Users/georgeskhawam/Projects/tagslut`

## A) ONLINE STEPS (do these before going offline)

### Quick interactive pipeline (recommended)
If you want a single command that prompts for the root folder and runs the full pipeline:
```bash
cd /Users/georgeskhawam/Projects/tagslut
export PYTHONPATH=.
tools/review/process_root.py
```

Notes:
- It **auto‑sets trust** (pre/post = 3) and will not prompt.
- It runs integrity with `--execute` so `flac_ok` is written.
- It runs hoarding enrichment, genre normalization, tag writes, art embedding, and promote/replace.

1) Download from Tidal (online)
```bash
TIDDL_BIN=/Users/georgeskhawam/.local/pipx/venvs/tiddl/bin/tiddl \
/Users/georgeskhawam/Projects/tagslut/tools/tiddl download \
  --path /Users/georgeskhawam/Music/tiddl \
  --scan-path /Users/georgeskhawam/Music/tiddl \
  url https://tidal.com/album/XXXX/u
```

2) Register into DB (can be offline, but usually run immediately after download)
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 -m tagslut index register /Users/georgeskhawam/Music/tiddl \
  --source tidal \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --dj-only --no-prompt --execute
```

3) Enrich metadata from providers (online)
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 -m tagslut index enrich \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --hoarding \
  --providers beatport,deezer,apple_music,itunes \
  --path '/Users/georgeskhawam/Music/tiddl/%' \
  --zones staging \
  --execute
```

## B) OFFLINE STEPS (safe without internet)

4) Integrity check (writes `flac_ok`)
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 tools/review/check_integrity_update_db.py /Users/georgeskhawam/Music/tiddl \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --execute
```

5) Normalize genres (DB backfill)
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 tools/review/normalize_genres.py /Users/georgeskhawam/Music/tiddl \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --rules tools/rules/genre_normalization.json \
  --execute
```

6) Write normalized genre tags into FLAC files
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 tools/review/tag_normalized_genres.py /Users/georgeskhawam/Music/tiddl \
  --rules tools/rules/genre_normalization.json \
  --execute
```

7) Promote FLAC to master library (replace+merge)
```bash
PYTHONPATH=/Users/georgeskhawam/Projects/tagslut \
python3 tools/review/promote_replace_merge.py /Users/georgeskhawam/Music/tiddl \
  --dest /Volumes/MUSIC/LIBRARY \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --execute
```

8) Transcode **new tracks only** (from `MDL_NEW_TRACKS.m3u`) to DJSSD
```bash
python3 - <<'PY'
import os, subprocess
from pathlib import Path

SRC_ROOT = Path('/Volumes/MUSIC/LIBRARY')
DST_ROOT = Path('/Volumes/DJSSD/DJ_LIBRARY_MP3')
M3U = Path('/Volumes/MUSIC/LIBRARY/MDL_NEW_TRACKS.m3u')

lines = [l.strip() for l in M3U.read_text(encoding='utf-8', errors='replace').splitlines()]
paths = []
seen = set()
for l in lines:
    if not l or l.startswith('#'):
        continue
    p = Path(l)
    if p in seen:
        continue
    seen.add(p)
    paths.append(p)

for src in paths:
    if not src.exists():
        continue
    try:
        rel = src.relative_to(SRC_ROOT)
    except Exception:
        continue
    out = (DST_ROOT / rel).with_suffix('.mp3')
    out.parent.mkdir(parents=True, exist_ok=True)

    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        continue

    tmp = out.with_suffix('.tmp.mp3')
    cmd = [
        'ffmpeg','-hide_banner','-loglevel','error','-stats','-y',
        '-i', str(src),
        '-map','0:a','-map','0:v?','-map_metadata','0',
        '-c:a','libmp3lame','-b:a','320k','-minrate','320k','-maxrate','320k','-bufsize','320k',
        '-id3v2_version','3','-write_id3v1','1',
        '-c:v','copy','-disposition:v','attached_pic',
        str(tmp)
    ]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        if tmp.exists():
            tmp.unlink()
        continue
    os.replace(tmp, out)
PY
```

9) Update MP3 playlists (mirror the kept M3U names)
Use this pattern when you’re ready to mirror the FLAC playlists on DJSSD:
```bash
# Example: mirror DJ_SET_POOL_4TO12.m3u to DJSSD paths
python3 - <<'PY'
from pathlib import Path

src_m3u = Path('/Volumes/MUSIC/LIBRARY/DJ_SET_POOL_4TO12.m3u')
dst_m3u = Path('/Volumes/DJSSD/DJ_SET_POOL_4TO12.m3u')

src_root = '/Volumes/MUSIC/LIBRARY/'
dst_root = '/Volumes/DJSSD/DJ_LIBRARY_MP3/'

lines = [l.strip() for l in src_m3u.read_text(encoding='utf-8', errors='replace').splitlines()]
paths = [l for l in lines if l and not l.startswith('#')]

mapped = [p.replace(src_root, dst_root).rsplit('.',1)[0] + '.mp3' for p in paths]
dst_m3u.write_text('\n'.join(mapped) + ('\n' if mapped else ''), encoding='utf-8')
PY
```

## C) LEXICON + REKORDBOX (offline)

10) Lexicon import
- Import folder: `/Volumes/DJSSD/DJ_LIBRARY_MP3`

11) Rekordbox import + analysis
- Import MP3 library root
- Analyze BPM/beatgrid/phrase
- Disable **Preferences → Advanced → Write tags to file**

12) Export to USB
- Rekordbox Export Mode → export to `/Volumes/DJSSD`

---

## Notes
- **Genre/BPM/Key** are written into the DB during enrichment; tags are only written into files by steps 5–6.
- Transcode step preserves artwork and uses ID3v2.3 (best Rekordbox compatibility).
- If you go fully offline, just skip Step A3 (enrich) until you’re back online.

## Advanced Procedures

## 14) Unknown Reduction (Head-On, No Qobuz)

Use this when `duration_status=unknown` is too high.

```bash
## 15) False Fail Reassessment (Extended/Remix Mismatch)

Use this for "audio is fine but marked fail" cases.

```bash
python scripts/reassess_duration_variant_mismatch.py \
  --db "$TAGSLUT_DB" \
  --execute
```

Then refresh playlists:

```bash
poetry run tagslut report m3u "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --source library \
  --m3u-dir "$LIBRARY_ROOT" \
  --merge
```
## 16) Playlist Audit Against DB (XLSX)

```bash
## 17) Rekordbox Conversion (Whole Playlist, Deduped, 320 CBR)

```bash
export SRC_M3U="$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES.m3u"
export OUT_MP3="$HOME/Music/Rekordbox_MP3_320"

python scripts/convert_m3u_to_mp3_320.py \
  --input-m3u "$SRC_M3U" \
  --output-root "$OUT_MP3" \
  --dedupe \
  --bitrate 320 \
  --cbr
```

Cover embed pass (if source contains art):

```bash
python scripts/embed_artwork_from_sources.py \
  --source-m3u "$SRC_M3U" \
  --target-m3u "$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES_FULL_MP3_320.m3u"
```
## 18) Relink After Picard Renames (Lightweight New DB Flow)

```bash
export RELINK_DB="/path/to/your/tagslut_db/EPOCH_2026-02-10_RELINK/music.db"

python scripts/bootstrap_relink_db.py \
  --from-db "/path/to/your/tagslut_db/EPOCH_2026-02-08/music.db" \
  --to-db "$RELINK_DB"

poetry run tagslut index register \
  "$LIBRARY_ROOT" \
  --db "$RELINK_DB" \
  --source relink \
  --execute
```
## 19) Dropbox Promotion + Cloud Deletion Safety

```bash
export DBX_LOCAL="/Volumes/bad/dbx/Dropbox"
export DBX_TOKEN_FILE="$HOME/dbtoken.txt"
## 20) Daily “No-Pollution” Policy

- Always precheck links against DB before download.
- Never promote without duration-check.
- Keep providers restricted to `beatport,tidal` unless explicitly needed.
- Treat `warn/fail` as review queues, not auto-delete signals.
- Rebuild Roon playlists from DB statuses after each major run.
