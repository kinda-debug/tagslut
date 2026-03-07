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
# Scan-only (asset-level)
python -m tagslut intake process-root \
  --db <V3_DB> \
  --root <PROMOTE_ROOT> \
  --scan-only

# Full pipeline
python -m tagslut intake process-root \
  --db <V3_DB> \
  --root <PROMOTE_ROOT>
```

## Primary Downloader
For day-to-day downloads, use the umbrella wrapper instead of stitching phases together manually.

```bash
# Default: precheck + download + local tag prep + promote + merged M3U
tools/get <provider-url>

# Also build DJ MP3 copies
tools/get <provider-url> --dj

# Skip tagging/enrich/art when intentionally doing a lighter run
tools/get <provider-url> --no-hoard
```

Notes:
- `tools/get` is the primary user-facing downloader for Beatport and Tidal.
- local identify/tag prep runs before promote; external enrich + cover art now launch in the background after promote
- `tools/get --m3u` writes Roon-style playlists inside `PLAYLIST_ROOT` using relative paths.
- `tools/get --dj` writes DJ playlists inside `DJ_PLAYLIST_ROOT` using absolute paths for Rekordbox/Lexicon.
- `tools/get-intake` is the advanced/backend command for existing batch roots, `--m3u-only`, and direct pipeline control.
- `tools/get-sync` is a deprecated Beatport compatibility alias.

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
