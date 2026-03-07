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
export DJ_PLAYLIST_ROOT="${DJ_PLAYLIST_ROOT:-$DJ_LIBRARY}"
export SCAN_ROOT="${SCAN_ROOT:-$STAGING_ROOT}"
export PROMOTE_ROOT="${PROMOTE_ROOT:-$STAGING_ROOT}"
export COMPARE_ROOT="${COMPARE_ROOT:-${TAGSLUT_ARTIFACTS:-artifacts}/compare}"
```

Notes:
- `MASTER_LIBRARY` is the canonical master library stored as FLAC.
- `PLAYLIST_ROOT` is the Roon-visible playlist folder inside the master library. `tools/get` writes relative-path M3Us there.
- `DJ_LIBRARY` is the derived DJ library.
- `DJ_PLAYLIST_ROOT` is the DJ playlist destination. `tools/get --dj` writes absolute-path M3Us there for Rekordbox/Lexicon.
- `VOLUME_QUARANTINE` is the active quarantine/stash root. Default live path is `/Volumes/MUSIC/_work/quarantine`.
- `ROOT_BP` and `ROOT_TD` are the default provider batch roots used by `tools/get`.
- `LIBRARY_ROOT`, `VOLUME_LIBRARY`, `DJ_MP3_ROOT`, and `DJ_LIBRARY_ROOT` remain compatibility aliases.
- Eligible non-FLAC lossless inputs are inspected at scan time and converted to FLAC before registration.
- No separate archive library is assumed by this runbook.

## Primary Downloader
Use `tools/get` for normal provider downloads.

```bash
# Default: precheck + download + local tag prep + promote + merged M3U
tools/get <provider-url>

# Add DJ MP3 export
tools/get <provider-url> --dj

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
- `tools/get-intake` is the advanced/backend command for existing batch roots and `--m3u-only`.
- `tools/get-sync` is deprecated and kept only as a compatibility alias.

## Daily Scan
```bash
python -m tagslut intake process-root \
  --db <V3_DB> \
  --root <SCAN_ROOT> \
  --scan-only
```

## Full Pipeline
```bash
python -m tagslut intake process-root \
  --db <V3_DB> \
  --root <SCAN_ROOT>
```

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

## Invariant
Promotion must select the preferred asset whenever a preferred asset exists under the promoted root.

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
