You are an expert Python engineer working in the tagslut repository.

Goal:
Make `dj validate` a mandatory gate before `dj xml emit`. Currently `emit_rekordbox_xml()`
calls `_run_pre_emit_validation()` which runs `validate_dj_library()` internally, but:
1. The `--skip-validation` flag silently disables ALL checks with no warning.
2. There is no check that `dj validate` has been run and passed at a known DB state.
3. The pre-emit check runs validation inline but has no audit trail.

This change adds a lightweight `dj_validation_state` table that records the last
successful `dj validate` run and its DB state hash. `xml emit` checks this table
before proceeding and fails loudly (with actionable error) if validation is stale or
missing — unless `--skip-validation` is passed (which now emits a WARNING to stderr).

Read first (in order):
1. AGENT.md
2. .codex/CODEX_AGENT.md
3. docs/PROJECT_DIRECTIVES.md
4. tagslut/dj/admission.py             (validate_dj_library, DjValidationReport)
5. tagslut/dj/xml_emit.py              (emit_rekordbox_xml, _run_pre_emit_validation, _build_export_scope)
6. tagslut/cli/commands/dj.py          (dj_validate command, dj_xml_emit command)
7. tagslut/storage/v3/migrations/      (look at 0012 or 0013 for migration pattern)
8. docs/audit/MISSING_TESTS.md        (§12 "Pre-flight Validation Before XML Emit")

Verify before editing:
- poetry run pytest tests/dj/ -v --tb=short 2>&1 | tail -20

Constraints:
- Migrations must go through the migration runner. Do not ALTER TABLE directly on the DB.
- Do not modify schema.py without a corresponding migration file.
- No new runtime dependencies.
- `--skip-validation` must remain (emergency escape) but must now log a WARNING.
- Targeted pytest only.

---

## Change 1 — Migration: add `dj_validation_state` table

Write `tagslut/storage/v3/migrations/0014_dj_validation_state.py`.

Table DDL:
```sql
CREATE TABLE IF NOT EXISTS dj_validation_state (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    validated_at  TEXT    NOT NULL,
    state_hash    TEXT    NOT NULL,
    issue_count   INTEGER NOT NULL DEFAULT 0,
    passed        INTEGER NOT NULL DEFAULT 0,  -- 1 if validation passed
    summary       TEXT
);
```

The `state_hash` here is the same SHA-256 hash produced by `_build_export_scope()`
(the DJ DB state fingerprint), NOT the XML file hash. This allows emit to detect
whether admissions have changed since validation last ran.

Migration must:
- Create the table if it does not exist.
- Add the migration to `tagslut/storage/v3/migration_runner.py` if there is a
  registry list.

---

## Change 2 — Record validation result after `dj validate` passes

In `tagslut/dj/admission.py`, add a function:

```python
def record_validation_state(
    conn: sqlite3.Connection,
    *,
    state_hash: str,
    issue_count: int,
    passed: bool,
    summary: str | None = None,
) -> int:
    """Insert a dj_validation_state row. Returns the new row id."""
```

In `tagslut/cli/commands/dj.py`, in the `dj_validate` command, after
`validate_dj_library()` returns and `report.ok` is True:

1. Compute the state_hash by importing and calling `_build_export_scope()` from
   `tagslut.dj.xml_emit`. Pass `playlist_scope=None`.
2. Call `record_validation_state()` with the hash, issue_count=0, passed=True.
3. Commit the connection.
4. Print the state_hash to stdout alongside the existing success message.

When validation FAILS, also record the state with passed=False and issue_count set.
This ensures the table always has a current row even after a failed run.

---

## Change 3 — Gate `xml emit` on a recent passed validation

In `tagslut/dj/xml_emit.py`, update `_run_pre_emit_validation()`:

```python
def _run_pre_emit_validation(conn: sqlite3.Connection) -> None:
    """
    1. Compute current DJ DB state_hash.
    2. Check dj_validation_state for a passed=1 row with matching state_hash.
    3. If not found, raise ValueError with actionable message.
    4. Run validate_dj_library() inline as a safety net.
    """
```

The actionable error message must be:
```
Pre-emit validation gate: no passing 'dj validate' run found for current DB state.
Run 'tagslut dj validate' first, then retry 'tagslut dj xml emit'.
(Current state_hash: <hash>)
```

If `dj_validation_state` table does not exist (old DB without migration), fall back
to the existing inline validation behavior with a deprecation warning.

Update `emit_rekordbox_xml()` — when `skip_validation=True`, emit this to stderr:
```
WARNING: --skip-validation bypasses DJ library integrity checks. Use only for emergencies.
```

---

## Change 4 — Tests in `tests/exec/test_dj_xml_preflight_validation.py`

Required tests:

1. `test_emit_requires_prior_validate_pass`
   Set up in-memory DB with one admitted track but NO dj_validation_state row.
   Call `emit_rekordbox_xml(..., skip_validation=False)`.
   Assert `ValueError` with "no passing 'dj validate' run" in message.

2. `test_emit_succeeds_after_validate_pass`
   Set up in-memory DB. Insert a dj_validation_state row with correct state_hash
   and passed=1. Call `emit_rekordbox_xml(...)`.
   Assert no ValueError is raised and XML file is written.

3. `test_emit_fails_when_state_hash_stale`
   Insert a dj_validation_state row with a DIFFERENT state_hash (wrong hash).
   Assert `ValueError` with "no passing 'dj validate' run" in message.

4. `test_emit_with_skip_validation_bypasses_gate`
   No dj_validation_state row. Call `emit_rekordbox_xml(..., skip_validation=True)`.
   Assert no ValueError is raised (gate bypassed).
   Assert that `sys.stderr` received the WARNING message (use `capsys`).

5. `test_validate_command_records_state_hash`
   Call `validate_dj_library()` on a clean DB (no issues).
   Call `record_validation_state()` with the resulting state_hash.
   Query `dj_validation_state` and assert passed=1 and state_hash matches.

6. `test_emit_fails_when_admission_added_after_validate`
   Run validate → records state_hash A.
   Add a new admission to the DB (state changes).
   Attempt emit → state_hash is now B ≠ A.
   Assert `ValueError` because no passing validation exists for state_hash B.

All tests must use in-memory SQLite with the full v3 schema + migration 0014 applied.
Use `create_schema_v3()` + `run_all_migrations()` helpers if available.

Required verification:
- poetry run pytest tests/exec/test_dj_xml_preflight_validation.py -v --tb=short
- poetry run pytest tests/dj/test_dj_pipeline_e2e.py -v --tb=short 2>&1 | tail -10

Done when: 6 tests pass, no regressions in E2E pipeline tests.

Commit: `feat(dj): make dj validate a mandatory gate before xml emit`
