# Hardcoded Path Inventory

This document tracks hardcoded paths that need to be replaced with environment variables or configuration settings.

## Critical Paths in Scripts

| Path | Occurrences | Target Variable |
| :--- | :--- | :--- |
| `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_20260119/music.db` | 30+ | `DEDUPE_DB` |
| `/Volumes/COMMUNE/M/Library` | 20+ | `VOLUME_LIBRARY` |
| `/Volumes/COMMUNE/M/_quarantine` | 10+ | `VOLUME_QUARANTINE` |
| `/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/` | 25+ | `DEDUPE_REPORTS` |

## Files to Refactor (Priority)

1.  **`tools/integrity/scan.py`**: Update to use `env_paths` for DB and logs.
2.  **`tools/decide/recommend.py`**: Update to use `env_paths` for DB.
3.  **`tools/decide/apply.py`**: Update to use `env_paths`, remove safety lock.
4.  **`tools/review/plan_removals.py`**: Update to use `env_paths`.
5.  **`tools/review/apply_removals.py`**: Update to use `env_paths`.
6.  **`tools/review/promote_by_tags.py`**: Update to use `env_paths`.
7.  **`config.toml`**: Update `[db] path` to use environment variable placeholder if supported, or rely on `env_paths` override.

## Documentation to Update

All `.md` files in `docs/` and root should eventually be updated or consolidated.
