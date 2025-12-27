# Migration Guide (2025 Refactor)

This document outlines the changes from the legacy script collection to the new modular architecture.

## Tool Mapping

| Legacy Script | New Tool | Notes |
| :--- | :--- | :--- |
| `tools/scan_flac_integrity.py` | `tools/integrity/scan.py` | Now integrates directly with DB upsert. |
| `dedupe/deduper.py` | `tools/decide/recommend.py` | Logic moved to `dedupe.core.decisions`. |
| `scripts/python/rank_duplicates.py` | `tools/decide/recommend.py` | Ranking logic is now deterministic in core. |
| `scripts/shell/apply_dedupe_plan.sh` | `tools/decide/apply.py` | Now consumes JSON plans instead of text files. |

## Database Migration

The new system uses a stricter SQLite schema. 

1.  **Compatibility**: The new `dedupe.storage` layer is designed to be **additive**. It will open existing databases and add missing columns (e.g., `flac_ok`, `metadata_json`) automatically upon the first `scan.py` run.
2.  **Backup**: Always backup your existing `.sqlite` files before running the new tools.

## Workflow Changes

**Old Workflow:**
1.  Run loose scripts to generate CSVs.
2.  Manually inspect CSVs.
3.  Run shell scripts to parse CSVs and move files.

**New Workflow:**
1.  **Scan**: `python tools/integrity/scan.py ...` (Populates DB)
2.  **Plan**: `python tools/decide/recommend.py -o plan.json` (Generates readable JSON)
3.  **Apply**: `python tools/decide/apply.py plan.json` (Executes deletions safely)

## API Changes (For Developers)

* **No Global State**: All functions now require explicit arguments (e.g., `db_conn`).
* **Typed Models**: Dictionary passing is replaced by `dedupe.storage.models.AudioFile`.
* **Logging**: `print()` calls replaced by structured `logging`.
