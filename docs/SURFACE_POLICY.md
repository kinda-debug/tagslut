# Surface Policy - tagslut (2026-03-02)

## Purpose

Define the supported command/script surface during v3 migration so operators and contributors use one logical path.

## Canonical Surface (Use For New Work)

1. `poetry run tagslut intake ...` - pre-check + download orchestration
2. `poetry run tagslut index ...` - inventory management
3. `poetry run tagslut decide ...` - quality-based planning
4. `poetry run tagslut execute ...` - move-only plan execution
5. `poetry run tagslut verify ...` - receipt and parity checks
6. `poetry run tagslut report ...` - M3U, duration, and DJ pool diff reports
7. `poetry run tagslut auth ...` - provider credential management
8. `poetry run tagslut dj ...` - DJ library curation and USB export
9. `poetry run tagslut gig ...` - gig set build and management
10. `poetry run tagslut export ...` - USB / DJ pool export
11. `poetry run tagslut init ...` - first-run initialization wizard

Reference map:
- `docs/SCRIPT_SURFACE.md`
- `docs/archive/legacy-root-docs-2026-03-06-md-cleanup/MOVE_EXECUTOR_COMPAT.md` (archived compatibility contract)

Branding note:
- `tagslut` is the preferred CLI brand.
- `dedupe` is a deprecated alias for `tagslut` and is still shipped.
- `dedupe` remains supported as a compatibility alias until 2026-06-01.

## Transitional Surface

Transitional wrappers have been retired from top-level CLI exposure.

Retired in Phase 5:
1. `tagslut scan`
2. `tagslut recommend`
3. `tagslut apply`
4. `tagslut promote`
5. `tagslut quarantine ...`
6. `tagslut mgmt ...`
7. `tagslut metadata ...`
8. `tagslut recover ...`

Top-level commands hidden by policy until promoted:
1. `tagslut canonize ...`
2. `tagslut enrich-file ...`
3. `tagslut explain-keeper ...`
4. `tagslut show-zone ...`
5. `tagslut recovery ...`

## Removal Horizon

- Warning period starts: February 9, 2026
- Target archival/removal window: June-July 2026 (aligned to `docs/archive/REDESIGN_TRACKER.md` Phase 5)
- Dated decommission plan: `docs/archive/phase-specs-2026-02-09/PHASE5_LEGACY_DECOMMISSION.md`

## Phase 5 Decommission Gates

Compatibility wrappers were removed after satisfying these gates:

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
3. `poetry run tagslut --help`
4. `poetry run tagslut intake --help`
5. `poetry run tagslut index --help`
6. `poetry run tagslut decide --help`
7. `poetry run tagslut execute --help`
8. `poetry run tagslut verify --help`
9. `poetry run tagslut report --help`
10. `poetry run tagslut auth --help`
11. `poetry run tagslut dj --help`
12. `poetry run tagslut gig --help`
13. `poetry run tagslut export --help`
14. `poetry run tagslut init --help`
15. Move executor contract doc: `docs/archive/legacy-root-docs-2026-03-06-md-cleanup/MOVE_EXECUTOR_COMPAT.md`
16. V3 parity validator: `python scripts/validate_v3_dual_write_parity.py --db <db> --strict`
17. Policy profile lint: `python scripts/lint_policy_profiles.py`
18. Phase 3 executor tests: `pytest -q tests/test_exec_engine_phase3.py tests/test_exec_receipts_phase3.py`

CI integration:
- `.github/workflows/test.yml` runs `scripts/audit_repo_layout.py` on push/PR.

## Change Control

Any change to canonical or transitional surface must update all of:
- `docs/SCRIPT_SURFACE.md`
- `docs/SURFACE_POLICY.md`
- `docs/archive/legacy-root-docs-2026-03-06-md-cleanup/MOVE_EXECUTOR_COMPAT.md` (if move execution contract changes)
- `docs/archive/phase-specs-2026-02-09/` (if phase runbook or decommission contract changes)
- `docs/archive/REDESIGN_TRACKER.md` (if milestone impact)
