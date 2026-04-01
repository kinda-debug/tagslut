# Prompt: DJ MP3 Reconcile Repair

## Context

Repo: `kinda-debug/tagslut`  
Branch: `dev`  
Canonical doc: `docs/DJ_PIPELINE.md` §Stage 2, `docs/DJ_WORKFLOW.md` §Stage 2

`tagslut mp3 reconcile` is Stage 2 of the DJ pipeline. It matches MP3 files
already on disk to `track_identity` rows in the v3 DB via ISRC (preferred) or
normalised artist+title, then registers each match as an `mp3_asset` row.

## Problem Statement

The command fails or produces zero matches in practice. The suspected failure
modes, in priority order:

1. **ISRC match path** — `mp3_asset` INSERT or UPDATE fails with a schema error
   because a column referenced in the INSERT does not exist in migration 0010,
   or the column name is wrong (e.g. `asset_path` vs `file_path`).
2. **Fallback title+artist normalisation** — the normalised match does not strip
   remix tags, featured artist parens, or leading articles consistently with the
   normalisation already applied to `track_identity.canonical_title /
   canonical_artist`.
3. **Dry-run default not honoured** — `--dry-run` is the documented default but
   the implementation may be applying writes anyway, or vice-versa.
4. **`mp3-root` path resolution** — `$DJ_LIBRARY` env var is resolved at the
   wrong point (after the arg parser rather than before), so the path is empty
   when the env var is set but not exported before the poetry shell.

## Files To Read First

- `tagslut/exec/mp3_reconcile.py` (primary)
- `tagslut/storage/migrations/0010_add_dj_pipeline_tables.sql`
- `tagslut/storage/v3/schema.py` — confirm `mp3_asset` column names
- `tests/exec/test_mp3_reconcile.py` (if it exists)

## Required Changes

1. Read the `mp3_asset` DDL from migration 0010 and cross-check every column
   name used in the INSERT inside `mp3_reconcile.py`. Fix any mismatch.
2. Verify that `--dry-run` is `True` by default in the argparse definition and
   that no write path is reachable without an explicit `--execute` flag.
3. Confirm that the ISRC comparison strips whitespace and is case-insensitive on
   both sides.
4. The normalisation function used for artist+title fallback must match the
   function (or call the same utility) used when `track_identity` rows were
   written. Identify that utility and ensure both sides call it.
5. Env var resolution: if `--mp3-root` is not supplied, the default must be
   evaluated lazily (i.e. `os.environ.get('DJ_LIBRARY')` at call time, not at
   module import time).

## Verification

```bash
# dry-run must produce match counts with zero DB writes
poetry run tagslut mp3 reconcile \
  --db "$TAGSLUT_DB" \
  --mp3-root "$DJ_LIBRARY" \
  --dry-run

# execute must register rows
poetry run tagslut mp3 reconcile \
  --db "$TAGSLUT_DB" \
  --mp3-root "$DJ_LIBRARY" \
  --execute

# confirm rows written
sqlite3 "$TAGSLUT_DB" "SELECT status, COUNT(*) FROM mp3_asset GROUP BY 1;"
```

## Constraints

- Do NOT alter the `mp3_asset` schema. Fix the code to match the schema.
- Do NOT change dry-run semantics — dry-run must never write.
- Do NOT change the CLI flag names.
- Run `poetry run mypy tagslut/exec/mp3_reconcile.py --ignore-missing-imports`
  and resolve any errors before committing.
- Run existing tests: `poetry run pytest tests/ -k mp3 --tb=short -q`

## Commit Message

```
fix(dj): repair mp3 reconcile column mismatch, dry-run default, ISRC normalisation
```
