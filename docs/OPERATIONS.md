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
export SCAN_ROOT="${SCAN_ROOT:-$VOLUME_STAGING}"
export PROMOTE_ROOT="${PROMOTE_ROOT:-$VOLUME_STAGING}"
```

Notes:
- `MASTER_LIBRARY` is the canonical FLAC library.
- `DJ_LIBRARY` is the derived DJ library.
- `LIBRARY_ROOT`, `VOLUME_LIBRARY`, `DJ_MP3_ROOT`, and `DJ_LIBRARY_ROOT` remain compatibility aliases.
- No separate archive library is assumed by this runbook.

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
