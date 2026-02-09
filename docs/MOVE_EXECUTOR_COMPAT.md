# Move Executor Compatibility Contract (Phase 3)

## Purpose

Define the compatibility layer between legacy move callers and the centralized
`dedupe.exec` engine introduced in Phase 3.

## Contract

Central executor:
- `dedupe/exec/engine.py`
- Contract version: `move_exec.v2`

Compatibility adapter:
- `dedupe/exec/compat.py`
- Adapter API: `execute_move_action(src, dest, execute, collision_policy="skip")`
- Adapter contract version: `move_exec_adapter.v1`

Plan receipt helpers:
- `dedupe/exec/receipts.py`
- `record_move_receipt(...)`
- `update_legacy_path_with_receipt(...)`

Required behavior:
1. Move-only semantics (no copy mode).
2. Dry-run by default (`execute=False`).
3. No destination overwrite.
4. Post-move verification (`size_eq`) with receipt verification hooks.
5. Structured receipt hash emitted for audit/event logs.
6. Legacy DB path mutation only after a `move_execution` receipt with `status=moved`.

Result states:
- `dry_run`
- `moved`
- `skip_missing`
- `skip_dest_exists`
- `error`

## Current Adapter Consumers

1. `tools/review/move_from_plan.py`
2. `tools/review/quarantine_from_plan.py`

Both scripts must route file moves through `execute_move(...)` and persist
receipts via `record_move_receipt(...)`.

## Additional Active Move Path

`tools/review/promote_by_tags.py` uses:
- `dedupe/utils/file_operations.py`
- `FileOperations.safe_move(...)`

Required for this path:
1. Verification before source deletion (`size_eq` plus optional checksum verification).
2. Structured JSONL audit events with `event=file_move`.
3. Operator-selectable log location via `--move-log`.

## Enforcement

`scripts/audit_repo_layout.py` enforces:
1. Active move executors import `execute_move` from `dedupe.exec`.
2. Active move executors do not use direct `shutil.move(...)` or `os.replace(...)`.
3. `promote_by_tags.py` routes moves through `FileOperations` with `--move-log` support.
4. `file_operations.py` emits structured `file_move` audit events with verification metadata.
5. This contract document remains present in `docs/`.

Run locally:

```bash
poetry run python scripts/audit_repo_layout.py
```

## Migration Note

`dedupe/exec/compat.py` remains for legacy callers. New execution code should
use `dedupe.exec.execute_move` and receipt helpers directly.
