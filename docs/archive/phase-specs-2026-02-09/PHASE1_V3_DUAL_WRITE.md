# Phase 1 - V3 Data Model + Dual-Write

## Scope

Phase 1 introduces v3 migration tables and optional dual-write from active
register/move execution flows.

## New V3 Tables

`tagslut/storage/schema.py` now initializes:

1. `asset_file`
2. `track_identity`
3. `asset_link`
4. `provenance_event`
5. `move_plan`
6. `move_execution`

## Dual-Write Flag

Dual-write is gated and disabled by default.

Enable with either:

1. env: `TAGSLUT_V3_DUAL_WRITE=1`
2. config: `tagslut.v3.dual_write = true`

## Dual-Write Entry Points

When enabled:

1. `tagslut mgmt register ... --execute`
   - writes legacy `files`
   - writes v3 `asset_file` / `track_identity` / `asset_link`
   - writes v3 `provenance_event` (`event_type=registered`)

2. `tools/review/move_from_plan.py --db ...`
   - writes legacy `files` path updates
   - writes v3 `move_plan` / `move_execution` / `provenance_event`
   - updates v3 `asset_file` path on successful moves

3. `tools/review/quarantine_from_plan.py --db ...`
   - same dual-write behavior for quarantine moves

## Backfill + Validation Scripts

1. Identity/link backfill:

```bash
python scripts/backfill_v3_identity_links.py --db <db> --execute
```

2. Provenance/move backfill from JSONL logs:

```bash
python scripts/backfill_v3_provenance_from_logs.py --db <db> --logs artifacts --execute
```

3. Parity validation:

```bash
python scripts/validate_v3_dual_write_parity.py --db <db> --strict
```

## Makefile Shortcuts

1. `make backfill-v3-identities DB=<db> EXECUTE=1`
2. `make backfill-v3-provenance DB=<db> LOGS=artifacts EXECUTE=1`
3. `make validate-v3-parity DB=<db> STRICT=1`
