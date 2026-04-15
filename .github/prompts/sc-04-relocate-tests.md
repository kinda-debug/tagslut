# Codex Prompt: Relocate misplaced root-level tests into subdirectories

**Repo**: `kinda-debug/tagslut` | **Branch**: `dev`
**Save to**: `.github/prompts/sc-04-relocate-tests.md`

---

## Context

10 test files live at `tests/` root but belong under the subdirectory that
matches their subject module. They were likely created before the
`tests/storage/v3/`, `tests/dj/`, and `tests/exec/` subdirectories existed.
Having them at root creates ambiguity about where new related tests should go
and makes `pytest tests/<subdir>/` targeting unreliable.

Files to move and their proposed destinations:

| Current path | Destination |
|---|---|
| `tests/test_backfill_identity_v3.py` | `tests/storage/v3/` |
| `tests/test_check_promotion_preferred_invariant_v3.py` | `tests/storage/v3/` |
| `tests/test_db_v3_schema.py` | `tests/storage/v3/` |
| `tests/test_identity_service.py` | `tests/storage/v3/` |
| `tests/test_identity_status_v3.py` | `tests/storage/v3/` |
| `tests/test_preferred_asset_v3.py` | `tests/storage/v3/` |
| `tests/test_migrate_v2_to_v3.py` | `tests/storage/` |
| `tests/test_migration_isrc.py` | `tests/storage/` |
| `tests/test_build_pool_v3.py` | `tests/dj/` |
| `tests/test_export_dj_candidates_v3.py` | `tests/dj/` |

---

## Grounding pass (stop and report if any fail)

1. Confirm each source file in the table above exists at its current path.
   `ls tests/test_backfill_identity_v3.py` etc.
2. Confirm `tests/storage/v3/` exists as a directory. If not, it must be
   created with an `__init__.py`.
3. Confirm `tests/storage/__init__.py` exists.
4. Confirm `tests/dj/__init__.py` exists.
5. Run `poetry run pytest tests/test_backfill_identity_v3.py -v --collect-only`
   to confirm the file is currently importable and collectable.
6. Read `.git/logs/HEAD` last 10 lines — confirm branch is `dev`.

If any grounding step fails, stop and report.

---

## Task

For each file in the table:

1. If the destination directory does not have an `__init__.py`, create one
   (empty file).
2. Use `git mv <source> <destination>` (not `mv`) so the rename is tracked in
   git history.
3. After all moves, run:
   ```
   poetry run pytest tests/storage/v3/ tests/storage/test_migrate_v2_to_v3.py tests/storage/test_migration_isrc.py tests/dj/test_build_pool_v3.py tests/dj/test_export_dj_candidates_v3.py -v
   ```
   All previously passing tests must still pass. If any fail due to import
   path issues (e.g. relative imports), fix the import — do not revert the
   move.
4. Confirm the old paths no longer exist:
   ```
   ls tests/test_backfill_identity_v3.py 2>&1  # should say "No such file"
   ```

---

## Edge cases

- If any file imports from `tests/conftest.py` using a relative path that
  breaks after the move, update the import to use the absolute
  `tests.conftest` path or rely on pytest's conftest auto-discovery (which
  already works at the `tests/` root level — no change needed).
- Do not touch files in `tests/__pycache__/` — these are regenerated
  automatically.
- Do not move `tests/test_migrate_v2_to_v3.py` to `tests/storage/v3/` — it
  belongs at `tests/storage/` because it covers the full migration path, not
  just v3-specific logic.

---

## Constraints

- Do not recreate any existing file.
- Do not modify any test logic — only relocate files and fix broken imports
  if the move causes them.
- Do not run the full test suite. Targeted only (the moved files).
- `git mv` only — never `cp` + `rm`.

---

## Commit

```
chore(tests): relocate 10 misplaced root-level v3/dj tests into matching subdirectories
```
