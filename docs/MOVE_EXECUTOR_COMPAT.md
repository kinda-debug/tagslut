# Move Executor Compatibility Contract

Canonical reference for the centralized move execution engine and its compatibility adapter.

## Contract Versions

| Version | Module | Role |
|---------|--------|------|
| `move_exec.v2` | `tagslut.exec.engine` | Canonical move executor with receipts and verification |
| `move_exec_adapter.v1` | `tagslut.exec.compat` | Legacy adapter preserving `MoveExecutionResult` shape |

New code must import from `tagslut.exec.engine` directly. The compat adapter exists only
for legacy callers and will be removed in a future release.

## Public API

### `execute_move(src, dest, *, execute, collision_policy)` → `MoveReceipt`

Canonical entry point. Performs safety checks, collision handling, and post-move verification.

### `execute_move_action(src, dest, *, execute, collision_policy)` → `MoveExecutionResult`

Legacy compatibility wrapper. Delegates to `execute_move()` and reshapes the receipt.

## Collision Policies

| Policy | Behaviour |
|--------|-----------|
| `skip` | Skip silently if destination exists |
| `dedupe` | Rename destination with content-hash suffix to avoid collision |
| `abort` | Raise `FileExistsError` if destination exists |

## Receipt Schema (`MoveReceipt`)

| Field | Type | Description |
|-------|------|-------------|
| `status` | `MoveStatus` | `moved`, `dry_run`, `skip_missing`, `skip_dest_exists`, `error` |
| `src` | `Path` | Source path at invocation time |
| `dest_requested` | `Path` | Requested destination path |
| `dest_final` | `Path \| None` | Actual destination (may differ under `dedupe` policy) |
| `execute` | `bool` | Whether the move was live or dry-run |
| `source_size` | `int \| None` | Source file size in bytes |
| `dest_size` | `int \| None` | Destination file size after move |
| `verification` | `str \| None` | Post-move verification status |
| `content_hash` | `str \| None` | Stable content hash for audit trail |
| `error` | `str \| None` | Error message if status is `error` |
| `executor_contract` | `str` | Contract version string |
| `timestamp` | `str` | ISO-8601 UTC timestamp |

## DB Mutation Rule

`files.path` may only be updated in the v3 DB when a `move_execution` receipt with
`status='moved'` exists. No DB path mutation without a successful receipt.

See `tagslut.exec.receipts` for the persistence layer.

## Verification Hooks

`verify_receipt(receipt)` enforces postconditions:

1. Source path no longer exists.
2. Destination path exists.
3. Source and destination sizes match.

## Caller Inventory

All plan execution scripts route through the centralized executor:

- `tools/review/move_from_plan.py`
- `tools/review/quarantine_from_plan.py`
- `tools/review/promote_by_tags.py`

Raw `shutil.move` / `os.replace` usage outside `tagslut.exec.engine` is prohibited.
`scripts/audit_repo_layout.py` enforces this constraint.

## Change Control

Updates to the move execution contract must co-update:

- `docs/MOVE_EXECUTOR_COMPAT.md` (this document)
- `docs/SURFACE_POLICY.md`
- `docs/SCRIPT_SURFACE.md`
