# Script Surface (Canonical vs Legacy)

This file is the authoritative map of where to run things in this repo.

Policy and deprecation rules are defined in:
- `docs/SURFACE_POLICY.md`

## Canonical Entry Points

1. `poetry run dedupe intake ...`
Role: Download/intake orchestration and prefilter operations.

2. `poetry run dedupe index ...`
Role: Inventory registration, duplicate checks, duration checks, and metadata enrichment for indexed files.

3. `poetry run dedupe decide ...`
Role: Policy-profile listing and deterministic plan generation.

4. `poetry run dedupe execute ...`
Role: Execute move/quarantine/promote workflows from plans.

5. `poetry run dedupe verify ...`
Role: Validate duration/recovery/parity and move receipt consistency.

6. `poetry run dedupe report ...`
Role: M3U and operational reports (duration, recovery, plan summaries).

7. `poetry run dedupe auth ...`
Role: Provider authentication and token lifecycle flows.

## Transitional / Compatibility CLI Wrappers

These still exist for backward compatibility:

- `dedupe mgmt ...`
- `dedupe metadata ...`
- `dedupe recover ...`

Legacy wrappers retired in Phase 5 (`P5-LEG-001..005`):
- legacy scan/recommend/apply/promote/quarantine CLI wrappers removed from top-level `dedupe` help surface

Use `dedupe intake/index/decide/execute/verify/report/auth` for new work.

## Recovery Command Status

- `dedupe recovery` is currently a minimal stub logger and does not implement the full move pipeline described in some historical docs.
- For move execution today, use:
  - Plan generation scripts in `tools/review/`
  - `tools/review/move_from_plan.py`
  - `tools/review/quarantine_from_plan.py`
  - `tools/review/promote_by_tags.py` (`--move-log` for JSONL move audit output)
- Compatibility contract for these executors:
  - `docs/MOVE_EXECUTOR_COMPAT.md`
  - `docs/PHASE1_V3_DUAL_WRITE.md` (dual-write + parity/backfill runbook)
  - `docs/PHASE2_POLICY_DECIDE.md` (policy profiles + deterministic planning contract)
  - `docs/PHASE3_EXECUTOR.md` (central executor + receipt mutation contract)
  - `docs/PHASE4_CLI_CONVERGENCE.md` (canonical command convergence and compatibility wrappers)
  - `docs/PHASE5_LEGACY_DECOMMISSION.md` (wrapper retirement tickets, gates, and timeline)

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
   - `poetry run dedupe index --help`
   - `poetry run dedupe execute --help`
   - `poetry run dedupe auth --help`
4. Keep generated runtime outputs under `artifacts/` (`artifacts/logs`, `artifacts/tmp`, `artifacts/db`) instead of repo root.
