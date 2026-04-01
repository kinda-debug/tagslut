# Prompt: DJ Validate + XML Emit Repair

## Context

Repo: `kinda-debug/tagslut`  
Branch: `dev`  
Canonical doc: `docs/DJ_PIPELINE.md` §Stage 3 (validate) and §Stage 4 (emit),
`docs/DJ_WORKFLOW.md` §Stage 3 and §Stage 4

`tagslut dj validate` writes a `dj_validation_state` row keyed by the current
DJ DB `state_hash`. `tagslut dj xml emit` refuses to proceed unless a passing
`dj_validation_state` row exists for that exact hash.

## Problem Statement

Either `dj validate` crashes before writing the row, or `dj xml emit` rejects
a valid passing row. Suspected failure modes in priority order:

1. **`state_hash` computation is non-deterministic** — if the hash is computed
   over a `SELECT` with no `ORDER BY`, the hash changes between identical DB
   states. Both `dj validate` and `dj xml emit` must use the same ordered query
   to compute the hash.
2. **`dj_validation_state` DDL missing** — migration 0010 may not include this
   table. If it is absent, `dj validate` raises `OperationalError: no such
   table`. Confirm the table exists in the migration SQL; add it if missing.
3. **`dj xml emit` state-hash lookup** — the lookup query in `xml_emit.py` may
   use a column name that does not match the DDL (`state_hash` vs `db_hash`
   etc.). Fix the mismatch.
4. **`--skip-validation` warning** — the doc says it prints to stderr when used.
   Verify this is implemented; add it if not.

## Files To Read First

- `tagslut/exec/dj_validate.py`
- `tagslut/exec/dj_xml_emit.py`
- `tagslut/storage/migrations/0010_add_dj_pipeline_tables.sql` — find or add
  `dj_validation_state` DDL
- `tests/exec/test_dj_validate.py` and `tests/exec/test_dj_xml_emit.py`
  (if they exist)

## Required Changes

1. Extract a shared `compute_dj_state_hash(conn)` utility function used by
   **both** `dj_validate.py` and `dj_xml_emit.py`. It must run:
   ```sql
   SELECT id FROM dj_admission ORDER BY id ASC
   ```
   and SHA-256 the concatenated IDs. Both files must import and call this
   function — not inline their own version.
2. If `dj_validation_state` is absent from migration 0010, add a new migration
   `0014_add_dj_validation_state.sql` with the DDL and register it in the
   migration runner. Do NOT alter the 0010 file.
3. Fix any column name mismatch in the validation-state lookup in
   `dj_xml_emit.py`.
4. In `dj_xml_emit.py`, if `--skip-validation` is passed, print:
   ```
   WARNING: --skip-validation bypasses the dj validate gate. Use only for emergencies.
   ```
   to `sys.stderr` before proceeding.

## Verification

```bash
# validate must exit 0 and print a passing summary
poetry run tagslut dj validate --db "$TAGSLUT_DB"

# emit must proceed without error after a passing validate
poetry run tagslut dj xml emit \
  --db "$TAGSLUT_DB" \
  --out /tmp/rekordbox_test.xml

# changing admissions after validate must cause emit to fail
sqlite3 "$TAGSLUT_DB" "DELETE FROM dj_admission WHERE id=(SELECT MAX(id) FROM dj_admission);"
poetry run tagslut dj xml emit --db "$TAGSLUT_DB" --out /tmp/rekordbox_test2.xml
# ^^^ must exit non-zero with a clear message about stale validation
```

## Constraints

- Do NOT alter existing migration files (0001–0013).
- `compute_dj_state_hash` must live in `tagslut/storage/v3/dj_state.py` (new
  file) and be imported by both exec modules.
- Run `poetry run mypy tagslut/exec/dj_validate.py tagslut/exec/dj_xml_emit.py
  tagslut/storage/v3/dj_state.py --ignore-missing-imports`.
- Run `poetry run pytest tests/ -k "validate or xml_emit" --tb=short -q`.

## Commit Message

```
fix(dj): shared state-hash utility, validate-gate column fix, skip-validation warning
```
