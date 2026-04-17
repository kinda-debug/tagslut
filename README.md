<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

# tagslut

## Project Overview
`tagslut` is a v3 music library operations system built around a deterministic database model.
It separates physical files from logical track identities, then applies deterministic selection and guarded promotion workflows.

## Core Concepts
- `asset`: a concrete file row (`asset_file`) with path and technical facts.
- `identity`: canonical track truth (`track_identity`) linked from assets via `asset_link`.
- `preferred asset`: one deterministic best asset per active identity (`preferred_asset`).
- `lifecycle status`: non-merged identities classified as `active`, `orphan`, or `archived` (`identity_status`).

## Operational Model
- Intake and scan update asset-level state.
- Identity linking and enrichment update identity-level state.
- Preferred asset computation materializes deterministic playback/promotion choices.
- Promotion moves files with post-run invariant checks.

## Quick Start

1. **Set up your environment:**
   ```bash
   source START_HERE.sh
   ```

2. **Learn the commands:**
   - [Documentation Index](docs/README.md) - Active docs, reference docs, and audit docs
   - [Operator Quick Start](docs/OPERATOR_QUICK_START.md) - Daily startup and operator workflow
   - [Workflows](docs/WORKFLOWS.md) - Current workflow contract and legacy archaeology
   - [Architecture](docs/ARCHITECTURE.md) - System shape and authoritative data model
   - [DJ Pool](docs/DJ_POOL.md) - Current M3U-based DJ pool workflow
   - [Download Strategy](docs/DOWNLOAD_STRATEGY.md) - Provider selection rules
   - [Ingestion Provenance](docs/INGESTION_PROVENANCE.md) - Provenance fields and vocabulary
   - [Multi-Provider ID Policy](docs/MULTI_PROVIDER_ID_POLICY.md) - Provider-ID reconciliation rules

Manual setup (legacy/reference):

```bash
cd <TAGSLUT_REPO>
source .venv/bin/activate

export V2_DB=<V2_DB>   # optional legacy DB (v2)
export V3_DB=<V3_DB>
export TAGSLUT_DB="$V3_DB"
export LIBRARY_ROOT=<LIBRARY_ROOT>
export STAGING_ROOT=<STAGING_ROOT>
export ROOT_BP="${ROOT_BP:-$STAGING_ROOT/bpdl}"
export ROOT_TD="${ROOT_TD:-$STAGING_ROOT/tidal}"
export PLAYLIST_ROOT="${PLAYLIST_ROOT:-$LIBRARY_ROOT/playlists}"
export DJ_PLAYLIST_ROOT="${DJ_PLAYLIST_ROOT:-$DJ_LIBRARY}"
export PROMOTE_ROOT="${PROMOTE_ROOT:-$STAGING_ROOT}"
```

## Standard Operations
```bash
# V3-safe staged-root processing
python -m tagslut intake process-root \
  --db <V3_DB> \
  --root <PROMOTE_ROOT> \
  --library <LIBRARY_ROOT> \
  --phases identify,enrich,art,promote,dj

# Preview only the DJ phase for an already-staged root
python -m tagslut intake process-root \
  --db <V3_DB> \
  --root <PROMOTE_ROOT> \
  --phases dj \
  --dry-run
```

Notes:
- On a v3 DB, `process-root` should be used with `identify,enrich,art,promote,dj`.
- `register`, `integrity`, and `hash` are legacy-scan phases and are blocked by the v3 guard when `--db` points at a v3 database.
- `--dry-run` currently previews the `dj` phase only.

## Primary Downloader
For day-to-day downloads, use the umbrella wrapper instead of stitching phases together manually.

```bash
# Default: precheck + download + local tag prep + promote + merged M3U
tools/get <provider-url>

# Spotify collection intake is supported too
tools/get "https://open.spotify.com/playlist/..."

# Skip tagging/enrich/art when intentionally doing a lighter run
tools/get <provider-url> --no-hoard

# Show internal paths, artifact files, and batch snapshots
tools/get <provider-url> --verbose
```

Notes:
- `tools/get` is the primary user-facing downloader for Spotify, Beatport, and Tidal.
- default output is concise; use `--verbose` for internal paths, artifact files, and batch snapshots
- local identify/tag prep runs before promote; external enrich + cover art now launch in the background after promote
- `tools/get --m3u` writes Roon-style playlists inside `PLAYLIST_ROOT` using relative paths.
- Spotify URLs are expanded before precheck, then acquired through the internal Spotify intake adapter with per-track service fallback (`qobuz -> tidal -> amazon`) and SpotiFLAC-style batch artifacts (log, failed report, manifest, and `.m3u8` for collections).
- if a run reports precheck/download zeros (`keep=0 skip=0 total=0`, `selected=0`), verify link extraction status before assuming duplicate suppression: check `artifacts/compare/precheck_links_extracted_*.csv` and `artifacts/compare/precheck_extracted_report_*.md` for notes such as `tidal_token_missing`
- work output is split by intent:
  - `FIX_ROOT` for salvageable metadata/tag issues (default: `/Volumes/MUSIC/_work/fix`)
  - `QUARANTINE_ROOT` / `$VOLUME_QUARANTINE` for risky files only (default: `/Volumes/MUSIC/_work/quarantine`)
  - `DISCARD_ROOT` for deterministic duplicates like `dest_exists` (default: `/Volumes/MUSIC/_work/discard`)
- expired quarantine can be reviewed or purged with `python tools/review/quarantine_gc.py --root "$QUARANTINE_ROOT" --days "$QUARANTINE_RETENTION_DAYS"`
- `--force-download` bypasses the pre-download skip so matched URLs are still fetched, but equal-or-better library files still win at promote time unless you run an explicit replacement workflow
- `tools/get-intake` is the advanced/backend command for existing batch roots, Spotify/Tidal direct intake, `--m3u-only`, and direct pipeline control.
- `tools/get-sync` is a deprecated Beatport compatibility alias.
- `tools/get --mp3` / `tools/get --dj` route to the canonical `tagslut intake url` orchestration to ensure the canonical source audio is tagged once before writing MP3 derivatives.

## 4-Stage DJ Pipeline

`tools/get --dj` is a convenience for URL → canonical source audio → MP3 derivatives. It does not replace the curated DJ pipeline below (admission/validation/XML).

For a curated DJ library, the only supported workflow is:
`tagslut intake` -> `tagslut mp3 build` or `tagslut mp3 reconcile` ->
`tagslut dj backfill` -> `tagslut dj validate` ->
`tagslut dj xml emit` or `tagslut dj xml patch`. See `docs/WORKFLOWS.md`, `docs/DJ_POOL.md`, and `docs/ARCHITECTURE.md` for the current contract and legacy context.

`MP3_LIBRARY` is the single canonical active MP3 asset root. `DJ_LIBRARY`
is a compatibility alias to the same root, not a separate operational library.
Preserved source/staging folders (for example `/Volumes/MUSIC/staging/Apple`,
`/Volumes/MUSIC/staging/Apple Music`, `/Volumes/MUSIC/_work`) are provenance-only.

Lexicon metadata should be imported from a `main.db` snapshot, preferably a
backup ZIP from `$HOME/Documents/Lexicon/Backups`. The importer matches
`Track.locationUnique` before `Track.location` and preserves Lexicon source
payloads in `track_identity.canonical_payload_json`.

Building a curated DJ library follows a deterministic 4-stage pipeline.
Each stage is safe to re-run and leaves explicit DB state as output.

```bash
# Stage 1: intake or refresh canonical masters
poetry run tagslut intake <provider-url>

# Stage 2: register existing MP3s against canonical identities and preserve provisional lineage
poetry run tagslut mp3 reconcile \
  --db "$TAGSLUT_DB" --mp3-root "$MP3_LIBRARY" --execute

# Stage 2 alternative: build DJ MP3s from canonical source assets
poetry run tagslut mp3 build \
  --db "$TAGSLUT_DB" --dj-root "$MP3_LIBRARY" --execute

# When building new MP3s from source audio, tagslut validates the ffmpeg output
# before accepting it: file must exist, be large enough, parse as MP3, and
# report a duration greater than 1 second.

# Stage 3: admit registered MP3s into the curated DJ library
poetry run tagslut dj backfill --db "$TAGSLUT_DB"

# Targeted one-off admission exists as `tagslut dj admit`, but it is not the primary Stage 3 path.

# Stage 3: validate DJ library state (missing files, empty metadata)
poetry run tagslut dj validate --db "$TAGSLUT_DB"

# Stage 4 requires a passing validation record for the current DB state.
# If admissions or playlists change after validation, rerun dj validate first.

# Stage 4: emit deterministic Rekordbox XML (stable TrackIDs across re-emits)
poetry run tagslut dj xml emit --db "$TAGSLUT_DB" --out rekordbox.xml

# Emergency only: --skip-validation bypasses the gate and prints a warning to stderr.

# After library changes: re-emit preserving Rekordbox cue points
poetry run tagslut dj xml patch --db "$TAGSLUT_DB" --out rekordbox_v2.xml
```

See `docs/README.md` for the active doc index, `docs/DJ_POOL.md` for the current DJ pool model, and `docs/WORKFLOWS.md` for legacy DJ/XML workflow context.

## Move Plan Execution

Use the canonical executor for reviewed plan CSVs:

```bash
python -m tagslut execute move-plan \
  --plan plans/example.csv \
  --db <V3_DB> \
  --dry-run
```

Execution writes receipts into the v3 move/provenance tables and also carries common per-track sidecars with the audio move.

## Maintainer PR Sync (Phase 1 stack)

Phase 1 status has advanced: PRs 9, 10, and 11 are already merged into `dev`.
The active gate is now PR 12 (identity merge).

Use `tools/review/sync_phase1_prs.sh` only when you intentionally need to refresh
legacy worktree branches for historical review workflows.

```bash
# Optional: override worktree paths
MIGRATION_WT=/tmp/tagslut_wt_migration \
IDENTITY_WT=/tmp/tagslut_wt_identity \
BACKFILL_WT=/tmp/tagslut_wt_backfill \
tools/review/sync_phase1_prs.sh
```

Current Phase 1 branch guidance:

- PR 12: prompt ready at `.github/prompts/phase1-pr12-identity-merge.prompt.md`
- PRs 13-15: prompts still required before execution
- Stale local backfill branch history was archived under
  `archive/fix-backfill-v3-stale-20260322`

When you want to refresh the stack only when new commits exist, run `tools/review/auto_sync_phase1_prs.sh`. It uses the same `MIGRATION_WT`, `IDENTITY_WT`, and `BACKFILL_WT` overrides, checks each worktree against its upstream, and executes `sync_phase1_prs.sh` only when the local branch is ahead (or the remote is missing). The helper aborts with an error if a remote already contains commits that are not present locally so you can reconcile manually.

## Safety Gates

- v3 doctor: schema and invariants
- migration verification: aggregate preservation checks
- promotion invariant guardrail: preferred-under-root must be selected when available

Safe promotion sequence:

```bash
make doctor-v3 V3=<V3_DB>
make check-promote-invariant V3=<V3_DB> ROOT=<PROMOTE_ROOT> MINUTES=240 STRICT=1
```

See [`docs/README.md`](docs/README.md) for the full documentation index.

## Repository Structure

- `tagslut/`: runtime packages and CLI
- `tools/`: operational wrappers and scripts
- `scripts/db/`: DB verification, reporting, lifecycle and guardrail scripts
- `docs/`: active documentation
- `docs/archive/`: historical and pre-v3 documents
- `tests/`: regression and invariant tests
