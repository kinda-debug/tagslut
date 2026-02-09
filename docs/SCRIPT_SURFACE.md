# Script Surface (Canonical vs Legacy)

This file is the authoritative map of where to run things in this repo.

## Canonical Entry Points

1. `poetry run dedupe mgmt ...`
Role: Inventory registration, duplicate pre-checks, duration checks, and M3U generation.

2. `poetry run dedupe metadata ...`
Role: Metadata provider authentication and enrichment workflows.

3. `poetry run dedupe recover ...`
Role: Corruption scan/repair/verify/report pipeline.

4. `tools/review/*.py`
Role: Operational plan-and-move scripts for promotion/quarantine/fingerprint review workflows.

5. `tools/get-intake`
Role: Unified download + fast intake orchestration (Beatport metadata prefilter, download, quick check, scan, fpcalc audit, plan, optional execute).

## Transitional / Legacy CLI Wrappers

These still exist for backward compatibility, but they route into `legacy/` code paths:

- `dedupe scan`
- `dedupe recommend`
- `dedupe apply`
- `dedupe promote`
- `dedupe quarantine ...`

Use `dedupe mgmt`, `dedupe metadata`, and `tools/review/*` for new work.

## Recovery Command Status

- `dedupe recovery` is currently a minimal stub logger and does not implement the full move pipeline described in some historical docs.
- For move execution today, use:
  - Plan generation scripts in `tools/review/`
  - `tools/review/move_from_plan.py`
  - `tools/review/quarantine_from_plan.py`

## Directory Ownership

- `dedupe/`: Productized CLI/package code.
- `tools/review/`: Active operational scripts.
- `legacy/tools/`: Archived historical scripts kept for reference and compatibility.
- `tools/review/promote_by_tags_versions/`: Historical snapshots.

## Rules for Keeping This Logical

1. New operational logic should go in `dedupe/` or `tools/review/`, not `legacy/`.
2. If a script is superseded, move it to an archive location and add a note in `legacy/tools/README.md`.
3. Keep docs aligned with real command help:
   - `poetry run dedupe --help`
   - `poetry run dedupe mgmt --help`
   - `poetry run dedupe metadata --help`
4. Keep generated runtime outputs under `artifacts/` (`artifacts/logs`, `artifacts/tmp`, `artifacts/db`) instead of repo root.
