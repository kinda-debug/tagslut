# Phase 3 - Central Move Executor

Phase 3 centralizes move execution and receipt persistence under `tagslut.exec`.

## What Was Added

1. Central executor
- `tagslut/exec/engine.py`
- API: `execute_move(src, dest, execute, collision_policy=...)`
- Receipt model: `MoveReceipt`
- Verification hook: `verify_receipt(receipt)`

2. Receipt persistence + path mutation contract
- `tagslut/exec/receipts.py`
- `record_move_receipt(...)`
- `update_legacy_path_with_receipt(...)`

3. Compatibility adapter retained
- `tagslut/exec/compat.py`
- Legacy API `execute_move_action(...)` now delegates to central executor.

4. Plan workflow integration
- `tools/review/move_from_plan.py` now uses `execute_move(...)`
- `tools/review/quarantine_from_plan.py` now uses `execute_move(...)`
- Both scripts now always write `move_execution` + `provenance_event` receipts when `--db` is provided.

## Contract

1. No direct DB path mutation without a successful move receipt.
2. `files.path` updates are allowed only when:
- receipt status is `moved`
- corresponding `move_execution` row exists with `status='moved'`

3. Receipt fields include:
- executor contract version
- stable receipt hash
- verification status/errors
- source/destination paths and size checks

## Compatibility

Legacy callers using `tagslut.exec.compat.execute_move_action(...)` remain
supported, but new code should import from `tagslut.exec` directly.

## Validation

Use:

```bash
poetry run python scripts/audit_repo_layout.py
poetry run python scripts/check_cli_docs_consistency.py
poetry run pytest -q tests/test_exec_engine_phase3.py tests/test_exec_receipts_phase3.py
```
