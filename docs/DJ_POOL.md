# DJ Pool Contract

DJ pool is a deterministic downstream export built from v3 identities.
It never mutates canonical library state.

## Inputs (only)
- `track_identity`
- `preferred_asset` + `asset_file`
- `identity_status`
- `dj_track_profile` (DJ-only decisions)

## Outputs
- export directory (DJ pool)
- `manifest.csv`
- `receipts.jsonl`
- optional export profile snapshot (JSON)

## Default Policy
- scope: active identities only
- require preferred asset: yes
- one asset per identity: yes
- overwrite: `if_same_hash`
- layout: `by_role` (fallback `unassigned`)
- format: `copy` (lossless), `mp3` optional

## Non-goals
- no canonical file moves
- no canonical tag rewrites
- no identity merges
- no "DJ pool as input truth"

## Operator Ladder
1. generate DJ candidates CSV
2. curate via `dj_track_profile`
3. export plan
4. export execute

## Commands
Generate candidates:
```bash
make dj-candidates V3=<V3_DB> OUT=output/dj_candidates.csv
```

Curate profile:
```bash
make dj-profile-set V3=<V3_DB> ID=<IDENTITY_ID> RATING=4 ENERGY=7 ROLE=builder ADD_TAG=groovy
```

Plan export (default):
```bash
make dj-pool-plan V3=<V3_DB> OUTDIR=<DJ_POOL_OUT>
```

Execute export (explicit):
```bash
make dj-pool-run V3=<V3_DB> OUTDIR=<DJ_POOL_OUT> EXECUTE=1 OVERWRITE=if_same_hash FORMAT=copy
```
