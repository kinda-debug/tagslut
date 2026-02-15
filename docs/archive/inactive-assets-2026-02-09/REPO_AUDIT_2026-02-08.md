# Repo Audit - 2026-02-08

## Scope

Audit focused on command surface, script organization, and repo hygiene with emphasis on tagslut operational scripts (`tools/review`) and legacy/archive overlap.

## Findings

1. Command/documentation drift:
- `docs/MGMT_MODE.md` mixes current behavior with historical option sets.
- `docs/V2_ARCHITECTURE.md` presents historical architecture as current.

2. Build helper drift:
- `Makefile` referenced non-existent commands (`tagslut sync`, quarantine subcommands not present).
- Promote targets pointed to legacy script path instead of active `tools/review` path.

3. Script surface ambiguity:
- Active scripts live in `tools/review/`, but legacy wrappers still exist in CLI.
- Duplicate basename `promote_by_tags.py` exists in both active and legacy trees.

4. Repo-root runtime artifact leakage:
- Runtime logs/csv outputs were present in root instead of under `artifacts/`.
- Expected `artifacts/db`, `artifacts/logs`, `artifacts/tmp` placeholders were missing.

## Changes Applied

1. Added canonical script map:
- `docs/SCRIPT_SURFACE.md`

2. Added script-area ownership docs:
- `tools/review/README.md`
- `legacy/tools/README.md`

3. Updated root README to current workflow and canonical script map:
- `README.md`

4. Modernized Makefile to real commands and safer helpers:
- `Makefile`

5. Added repository layout audit script:
- `scripts/audit_repo_layout.py`
- New target: `make audit-layout`

6. Added expected artifact directories and placeholders:
- `artifacts/db/.gitkeep`
- `artifacts/logs/.gitkeep`
- `artifacts/tmp/.gitkeep`

7. Moved root runtime outputs into `artifacts/` and restored layout test health.

8. Added status notes to historical docs:
- `docs/MGMT_MODE.md`
- `docs/V2_ARCHITECTURE.md`

## Validation

- `poetry run pytest -q tests/test_repo_structure.py` -> 12 passed
- `poetry run python scripts/audit_repo_layout.py` -> warnings only (no errors)

## Remaining Work (Recommended)

1. Decide single canonical promote implementation:
- Keep either `tools/review/promote_by_tags.py` or `legacy/tools/review/promote_by_tags.py` as primary; deprecate the other.

2. Resolve `tagslut recovery` mismatch:
- Either implement move pipeline in `tagslut recovery` or clearly route to plan/move scripts.

3. Split historical sections from `docs/MGMT_MODE.md`:
- Keep only currently supported options in main body.
- Move design history to an archived note.

4. Gradually retire legacy CLI wrappers (`scan`, `recommend`, `apply`, `promote`, `quarantine`) once replacement commands are stable.
