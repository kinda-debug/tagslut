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

# Also build DJ MP3 copies
tools/get <provider-url> --dj

# Skip tagging/enrich/art when intentionally doing a lighter run
tools/get <provider-url> --no-hoard

# Show internal paths, artifact files, and batch snapshots
tools/get <provider-url> --verbose
```

Notes:
- `tools/get` is the primary user-facing downloader for Beatport and Tidal.
- default output is concise; use `--verbose` for internal paths, artifact files, and batch snapshots
- local identify/tag prep runs before promote; external enrich + cover art now launch in the background after promote
- `tools/get --m3u` writes Roon-style playlists inside `PLAYLIST_ROOT` using relative paths.
- `tools/get --dj` writes DJ playlists inside `DJ_PLAYLIST_ROOT` using absolute paths for Rekordbox/Lexicon.
- work output is split by intent:
  - `FIX_ROOT` for salvageable metadata/tag issues (default: `/Volumes/MUSIC/_work/fix`)
  - `QUARANTINE_ROOT` / `$VOLUME_QUARANTINE` for risky files only (default: `/Volumes/MUSIC/_work/quarantine`)
  - `DISCARD_ROOT` for deterministic duplicates like `dest_exists` (default: `/Volumes/MUSIC/_work/discard`)
- expired quarantine can be reviewed or purged with `python tools/review/quarantine_gc.py --root "$QUARANTINE_ROOT" --days "$QUARANTINE_RETENTION_DAYS"`
- `--force-download` bypasses the pre-download skip so matched URLs are still fetched, but equal-or-better library files still win at promote time unless you run an explicit replacement workflow
- `tools/get-intake` is the advanced/backend command for existing batch roots, `--m3u-only`, and direct pipeline control.
- `tools/get-sync` is a deprecated Beatport compatibility alias.

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
Use `tools/review/sync_phase1_prs.sh` to push the three immediate branch updates while preserving branch/PR scope boundaries.

```bash
# Optional: override worktree paths
MIGRATION_WT=/tmp/tagslut_wt_migration \
IDENTITY_WT=/tmp/tagslut_wt_identity \
BACKFILL_WT=/tmp/tagslut_wt_backfill \
tools/review/sync_phase1_prs.sh
```

The script pushes:
- `fix/migration-0006` with `--force-with-lease` (PR #193)
- `fix/identity-service` with `--force-with-lease` (PR #185)
- `fix/backfill-v3` to remote branch `fix/dj-tag-enrichment` with `--force-with-lease`

After pushing, open the DJ enrichment PR targeting `fix/identity-service`:

```bash
gh pr create --base fix/identity-service --head fix/dj-tag-enrichment \
  --title "feat(dj): enrich FLAC DJ tags from v3 identity cache before transcode" \
  --draft
```

This keeps DJ enrichment separate from `fix/v3-backfill-command` (PR #186).

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
