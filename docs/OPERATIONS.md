<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

# Operations

This is the canonical operator guide for the v3 model.

## Canonical Surface (Use For New Work)
- `poetry run tagslut intake ...`
- `poetry run tagslut index ...`
- `poetry run tagslut decide ...`
- `poetry run tagslut execute ...`
- `poetry run tagslut verify ...`
- `poetry run tagslut report ...`
- `poetry run tagslut auth ...`

Compatibility aliases:
- `tools/tagslut` wraps `python -m tagslut`.

## Transitional Surface
- `validate_v3_dual_write_parity.py`
- `lint_policy_profiles.py`

## Environment
```bash
cd <TAGSLUT_REPO>
source .venv/bin/activate
set -a
source .env
set +a

export V3_DB="${V3_DB:-$TAGSLUT_DB}"
export MASTER_LIBRARY="${MASTER_LIBRARY:-${LIBRARY_ROOT:-$VOLUME_LIBRARY}}"
export STAGING_ROOT="${STAGING_ROOT:-$VOLUME_STAGING}"
export ROOT_BP="${ROOT_BP:-$STAGING_ROOT/bpdl}"
export ROOT_TD="${ROOT_TD:-$STAGING_ROOT/tidal}"
export PLAYLIST_ROOT="${PLAYLIST_ROOT:-$MASTER_LIBRARY/playlists}"
export MP3_LIBRARY="${MP3_LIBRARY:-/Volumes/MUSIC/MP3_LIBRARY}"
export DJ_PLAYLIST_ROOT="${DJ_PLAYLIST_ROOT:-$DJ_LIBRARY}"
export VOLUME_WORK="${VOLUME_WORK:-/Volumes/MUSIC/_work}"
export FIX_ROOT="${FIX_ROOT:-$VOLUME_WORK/fix}"
export QUARANTINE_ROOT="${QUARANTINE_ROOT:-${VOLUME_QUARANTINE:-$VOLUME_WORK/quarantine}}"
export DISCARD_ROOT="${DISCARD_ROOT:-$VOLUME_WORK/discard}"
export SCAN_ROOT="${SCAN_ROOT:-$STAGING_ROOT}"
export PROMOTE_ROOT="${PROMOTE_ROOT:-$STAGING_ROOT}"
export COMPARE_ROOT="${COMPARE_ROOT:-${TAGSLUT_ARTIFACTS:-artifacts}/compare}"
```

Notes:
- `MASTER_LIBRARY` is the canonical master library stored as FLAC.
- `MP3_LIBRARY` is the full-tag playback MP3 library derived from masters.
- `PLAYLIST_ROOT` is the Roon-visible playlist folder inside the master library. `tools/get` writes relative-path M3Us there.
- `DJ_LIBRARY` is the derived DJ library.
- `DJ_PLAYLIST_ROOT` is the DJ playlist destination.
- work output is split:
  - `FIX_ROOT=/Volumes/MUSIC/_work/fix` for salvageable metadata/tag issues
  - `QUARANTINE_ROOT` / `VOLUME_QUARANTINE=/Volumes/MUSIC/_work/quarantine` for risky files only
  - `DISCARD_ROOT=/Volumes/MUSIC/_work/discard` for deterministic duplicates like `dest_exists`
- `ROOT_BP` and `ROOT_TD` are the default provider batch roots used by `tools/get`.
- `LIBRARY_ROOT`, `VOLUME_LIBRARY`, `DJ_MP3_ROOT`, and `DJ_LIBRARY_ROOT` remain compatibility aliases.
- Eligible non-FLAC lossless inputs are inspected at scan time and converted to FLAC before registration.
- No separate archive library is assumed by this runbook.

## Primary Downloader
Use `tools/get` for normal provider downloads.

```bash
# Default: precheck + download + local tag prep + promote + merged M3U
tools/get <provider-url>

# Skip tagging/enrich/art
tools/get <provider-url> --no-hoard

# Show internal paths, artifacts, and batch snapshots
tools/get <provider-url> --verbose
```

Notes:
- `tools/get` is the primary user-facing downloader for Beatport and Tidal.
- default output is concise; add `--verbose` only when debugging the wrapper itself
- local identify/tag prep runs before promote; external enrich + cover art are launched in the background after promote
- `--force-download` downloads matched URLs anyway, but promotion still keeps an equal-or-better existing library file unless you intentionally run a replacement workflow
- expired quarantine can be reviewed or purged with `python tools/review/quarantine_gc.py --root "$QUARANTINE_ROOT" --days "$QUARANTINE_RETENTION_DAYS"`
- `tools/get-intake` is the advanced/backend command for existing batch roots and `--m3u-only`.
- `tools/get-sync` is deprecated and kept only as a compatibility alias.
- `tools/get --mp3` / `tools/get --dj` route to `tagslut intake url` orchestration (single enrich/writeback pass before MP3/DJ derivatives).

## DJ Pipeline (Canonical Workflow)

The canonical approach to building a curated DJ library is a deterministic 4-stage pipeline.
Each stage writes explicit DB state and is safe to re-run.

```bash
# Stage 1: intake or refresh canonical masters
poetry run tagslut intake <provider-url>

# Stage 2: register existing MP3s against canonical identities
poetry run tagslut mp3 reconcile \
  --db "$TAGSLUT_DB" --mp3-root "$DJ_LIBRARY" --execute

# Stage 3: admit registered MP3s into the DJ library
poetry run tagslut dj backfill --db "$TAGSLUT_DB"

# Stage 3: validate DJ library state
poetry run tagslut dj validate --db "$TAGSLUT_DB"

# If DJ admissions/playlists changed after validation, rerun this before Stage 4.

# Stage 4: emit deterministic Rekordbox XML
poetry run tagslut dj xml emit --db "$TAGSLUT_DB" --out rekordbox.xml

# Subsequent re-emit preserving existing Rekordbox cue points
poetry run tagslut dj xml patch --db "$TAGSLUT_DB" --out rekordbox_v2.xml
```

See `docs/DJ_PIPELINE.md` for the concise pipeline reference and `docs/DJ_WORKFLOW.md` for full per-stage documentation.

`dj xml emit` now checks for a passing `dj validate` record for the current DJ DB
state before it writes XML. `--skip-validation` remains available only as an
emergency bypass and prints a warning to stderr.

## V3 Staged-Root Processing

Use `tagslut intake process-root` only for the v3-safe staged-root phases:

```bash
python -m tagslut intake process-root \
  --db <V3_DB> \
  --root <PROMOTE_ROOT> \
  --library <MASTER_LIBRARY> \
  --phases identify,enrich,art,promote,dj
```

Preview just the DJ phase without writing FLAC tags or MP3s:

```bash
python -m tagslut intake process-root \
  --db <V3_DB> \
  --root <PROMOTE_ROOT> \
  --phases dj \
  --dry-run
```

Important:
- On a v3 DB, `register`, `integrity`, and `hash` are blocked by the `process-root` v3 guard.
- Use `tagslut index register` and `tools/review/check_integrity_update_db.py` directly when you intentionally need those legacy-scan behaviors.
- `--dry-run` currently applies to the DJ phase only.

## Safe Promotion
```bash
python -m tagslut intake process-root \
  --db <V3_DB> \
  --root <PROMOTE_ROOT> \
  --library <MASTER_LIBRARY> \
  --phases promote
```

Optional force controls (only when intentionally bypassing default guards):
```bash
python tools/review/promote_replace_merge.py \
  <PROMOTE_ROOT> \
  --db <V3_DB> \
  --dest <MASTER_LIBRARY> \
  --execute \
  --allow-duplicate-hash \
  --allow-non-ok-duration
```

## Move Plan Execution

Use the canonical executor for reviewed plan CSVs:

```bash
python -m tagslut execute move-plan \
  --plan plans/example.csv \
  --db <V3_DB> \
  --dry-run
```

Notes:
- writes `move_plan`, `move_execution`, and `provenance_event` rows
- `--verify` runs parity checks after execution
- common sidecars such as `.lrc`, `.cover.jpg`, and sibling artwork files move with the audio file

## Invariant
Promotion must select the preferred asset whenever a preferred asset exists under the promoted root.

## Maintainer Helper

For the active Phase 1 branch stack only:

```bash
tools/review/sync_phase1_prs.sh
```

## Required Gates
```bash
make doctor-v3 V3=<V3_DB>
make check-promote-invariant V3=<V3_DB> ROOT=<PROMOTE_ROOT> MINUTES=240 STRICT=1
```

## DB Maintenance
After pulling schema changes (new views/indexes), run once per DB:

```bash
make apply-v3-schema V3=<V3_DB>
```

## DJ Candidates (Read-Only CSV)
Generate downstream DJ candidates from v3 identities without modifying files:

```bash
make dj-candidates V3=<V3_DB> OUT=output/dj_candidates.csv LIMIT=200
```

Recommended defaults:
- keep `REQUIRE_PREFERRED=1`
- keep `STRICT=1`
- use `INCLUDE_ORPHANS=0` unless you explicitly need orphan review.

## DJ Missing Metadata Queue
Generate a CSV queue of DJ candidates missing BPM/key/genre/core fields for manual enrichment:

```bash
make dj-missing-metadata V3=<V3_DB> OUT=output/dj_missing_metadata.csv SCOPE=active LIMIT=200
```

Includes strong-key IDs (ISRC, Beatport, Traxsource, Spotify, Tidal, Deezer, MusicBrainz) to speed enrichment.

Example:
```bash
make dj-missing-metadata V3=<V3_DB> OUT=output/dj_missing_metadata_active.csv SCOPE=active LIMIT=200
```

## DJ Profiles (Write DJ Layer Only)
Contract reference: `docs/DJ_POOL.md` (downstream-only DJ pool boundary).

Mark one identity as DJ-ready without changing canonical metadata:

```bash
make dj-profile-set \
  V3=<V3_DB> \
  ID=<IDENTITY_ID> \
  RATING=4 ENERGY=7 ROLE=builder ADD_TAG=groovy NOTES="set A candidate"
```

Inspect one profile:

```bash
make dj-profile-get V3=<V3_DB> ID=<IDENTITY_ID>
```

Export ready list (candidates + DJ profile fields):

```bash
make dj-ready V3=<V3_DB> OUT=output/dj_ready.csv ONLY_PROFILED=1
```

Build deterministic DJ pool tree (safe plan by default):

```bash
make dj-pool-plan V3=<V3_DB> OUTDIR=<DJ_EXPORT_ROOT> MANIFEST=output/dj_export_manifest.csv
```

Execute copy export:

```bash
make dj-pool-run V3=<V3_DB> OUTDIR=<DJ_EXPORT_ROOT> EXECUTE=1 OVERWRITE=if_same_hash FORMAT=copy
```

Recommended layout:
- `LAYOUT=by_role` for set programming
- use a separate export root (never inside `MASTER_LIBRARY`)
- review manifest before execute.
