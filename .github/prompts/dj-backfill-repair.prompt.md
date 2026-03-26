# Prompt: DJ Backfill Repair

## Context

Repo: `kinda-debug/tagslut`  
Branch: `dev`  
Canonical doc: `docs/DJ_PIPELINE.md` §Stage 3, `docs/DJ_WORKFLOW.md` §Stage 3

`tagslut dj backfill` is the bulk Stage 3 admission path. It promotes all
`mp3_asset` rows with `status=verified` into `dj_admission` and ensures a
`dj_track_id_map` row exists for each admission. It is documented as idempotent
(already-admitted tracks must be skipped without error).

## Problem Statement

The command fails or silently admits zero rows. Suspected failure modes:

1. **`status` filter wrong** — the query filters on `status='verified'` but the
   actual value written by `mp3 reconcile` / `mp3 build` may be `'active'` or
   another string. Check what value `mp3_reconcile.py` writes on success.
2. **UNIQUE constraint on `dj_admission`** — re-running raises an IntegrityError
   instead of skipping existing rows. The INSERT must use
   `INSERT OR IGNORE` or an equivalent `ON CONFLICT DO NOTHING`.
3. **`dj_track_id_map` INSERT** — the auto-increment TrackID assignment may
   conflict if the same `dj_admission_id` is reprocessed. Must also be
   idempotent (`INSERT OR IGNORE`).
4. **Missing `--db` default** — if `$TAGSLUT_DB` is not set and no `--db` is
   passed, the command should fail loudly with an actionable message, not a
   Python traceback.

## Files To Read First

- `tagslut/exec/dj_backfill.py` (primary)
- `tagslut/storage/migrations/0010_add_dj_pipeline_tables.sql` — confirm
  `dj_admission` and `dj_track_id_map` DDL and any UNIQUE constraints
- `tagslut/exec/mp3_reconcile.py` — find the exact `status` string written on
  successful reconcile
- `tests/exec/test_dj_backfill.py` (if it exists)

## Required Changes

1. Align the `status` filter in `dj_backfill.py` with the exact string written
   by `mp3_reconcile.py`.
2. All INSERTs into `dj_admission` and `dj_track_id_map` must be idempotent.
   Use `INSERT OR IGNORE INTO` for both.
3. Add a clear error message when `--db` is not supplied and `$TAGSLUT_DB` is
   not set in the environment.
4. After the backfill loop, print a summary: `Admitted N new, skipped M
   existing.`

## Verification

```bash
# first run — should admit all verified mp3_asset rows
poetry run tagslut dj backfill --db "$TAGSLUT_DB"

# second run — must produce zero new admissions without error
poetry run tagslut dj backfill --db "$TAGSLUT_DB"

# confirm
sqlite3 "$TAGSLUT_DB" "
SELECT COUNT(*) FROM dj_admission;
SELECT COUNT(*) FROM dj_track_id_map;
"
```

## Constraints

- Do NOT change the `dj_admission` or `dj_track_id_map` schema.
- TrackID values already in `dj_track_id_map` must never be reassigned.
- Run `poetry run mypy tagslut/exec/dj_backfill.py --ignore-missing-imports`.
- Run `poetry run pytest tests/ -k backfill --tb=short -q`.

## Commit Message

```
fix(dj): idempotent backfill, align status filter, clear missing-db error
```
