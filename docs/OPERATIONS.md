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
cd <TAGSLLUT_REPO>
source .venv/bin/activate

export V3_DB=<V3_DB>
export LIBRARY_ROOT=<LIBRARY_ROOT>
export SCAN_ROOT=<PROMOTE_ROOT>
export PROMOTE_ROOT=<PROMOTE_ROOT>
```

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
make promote-safe \
  V3=<V3_DB> \
  ROOT=<PROMOTE_ROOT> \
  LIB=<LIBRARY_ROOT>
```

## Invariant
Promotion must select the preferred asset whenever a preferred asset exists under the promoted root.

## Required Gates
```bash
make doctor-v3 V3=<V3_DB>
make check-promote-invariant V3=<V3_DB> ROOT=<PROMOTE_ROOT> MINUTES=240 STRICT=1
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
