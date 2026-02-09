# Surface Policy - dedupe (2026-02-09)

## Purpose

Define the supported command/script surface during v3 migration so operators and contributors use one logical path.

## Canonical Surface (Use For New Work)

1. `poetry run dedupe intake ...`
2. `poetry run dedupe index ...`
3. `poetry run dedupe decide ...`
4. `poetry run dedupe execute ...`
5. `poetry run dedupe verify ...`
6. `poetry run dedupe report ...`
7. `poetry run dedupe auth ...`

Reference map:
- `docs/SCRIPT_SURFACE.md`

## Transitional Surface (Deprecated)

These wrappers remain temporarily for compatibility and now emit deprecation warnings:

1. `dedupe mgmt ...`
Recommended now: `dedupe index ...` and `dedupe report ...`

2. `dedupe metadata ...`
Recommended now: `dedupe auth ...` and `dedupe index enrich ...`

3. `dedupe recover ...`
Recommended now: `dedupe verify recovery ...` and `dedupe report recovery ...`

Retired in Phase 5 (`P5-LEG-001..005`):
- `dedupe scan`
- `dedupe recommend`
- `dedupe apply`
- `dedupe promote`
- `dedupe quarantine ...`

## Removal Horizon

- Warning period starts: February 9, 2026
- Target archival/removal window: June-July 2026 (aligned to `docs/REDESIGN_TRACKER.md` Phase 5)
- Dated decommission plan: `docs/PHASE5_LEGACY_DECOMMISSION.md`

## Phase 5 Decommission Gates

`mgmt/metadata/recover` wrappers can be removed only after:

1. Coverage parity gate:
- Canonical replacement command is documented and tested.

2. Burn-in gate:
- No operator docs require the wrapper path as primary flow.
- Deprecation window has elapsed (minimum 30 days since warning start).

3. Safety gate:
- `scripts/check_cli_docs_consistency.py` passes.
- `scripts/audit_repo_layout.py` passes.
- Canonical `decide/execute/verify/report` regression tests pass.

## Enforcement Rules

1. Do not add new user-facing commands under `legacy/`.
2. Do not introduce new top-level CLI wrappers that bypass canonical surfaces.
3. Keep runtime artifacts out of repo root; write to `artifacts/`.
4. Keep docs synchronized with live CLI help and script surface map.

## Validation Hooks

1. `poetry run python scripts/audit_repo_layout.py`
2. `poetry run python scripts/check_cli_docs_consistency.py`
3. `poetry run dedupe --help`
4. `poetry run dedupe intake --help`
5. `poetry run dedupe index --help`
6. `poetry run dedupe decide --help`
7. `poetry run dedupe execute --help`
8. `poetry run dedupe verify --help`
9. `poetry run dedupe report --help`
10. `poetry run dedupe auth --help`
6. Move executor contract doc: `docs/MOVE_EXECUTOR_COMPAT.md`
7. V3 parity validator: `python scripts/validate_v3_dual_write_parity.py --db <db> --strict`
8. Policy profile lint: `python scripts/lint_policy_profiles.py`
9. Phase 3 executor tests: `pytest -q tests/test_exec_engine_phase3.py tests/test_exec_receipts_phase3.py`

CI integration:
- `.github/workflows/test.yml` runs `scripts/audit_repo_layout.py` on push/PR.

## Change Control

Any change to canonical or transitional surface must update all of:
- `docs/SCRIPT_SURFACE.md`
- `docs/SURFACE_POLICY.md`
- `docs/MOVE_EXECUTOR_COMPAT.md` (if move execution contract changes)
- `docs/PHASE1_V3_DUAL_WRITE.md` (if dual-write contract changes)
- `docs/PHASE2_POLICY_DECIDE.md` (if policy/planning contract changes)
- `docs/PHASE3_EXECUTOR.md` (if execution receipt/DB mutation contract changes)
- `docs/PHASE4_CLI_CONVERGENCE.md` (if canonical command convergence changes)
- `docs/PHASE5_LEGACY_DECOMMISSION.md` (if decommission timeline/gates change)
- `docs/REDESIGN_TRACKER.md` (if milestone impact)
