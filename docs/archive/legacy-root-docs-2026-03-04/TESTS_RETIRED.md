# Retired Tests

## `tests/test_mgmt_workflow.py`

Retired during the audit cleanup because it exercises the hidden/retired `_mgmt` command group.

Rationale:
- `.claude/AGENTS.md` marks `mgmt` as a retired wrapper on the CLI surface.
- Canonical surfaces are: `intake`, `index`, `decide`, `execute`, `verify`, `report`, `auth`, `dj`, `gig`, `export`, and `init`.

## `tests/recovery/` -> `tests/archive/recovery/`

Archived during Prompt 4 (2026-03-02) after `tagslut/recovery` was moved out of
the live package and replaced with a deprecation stub.

Rationale:
- Recovery package implementation is now retained under `legacy/tagslut_recovery/`.
- Active CLI surface no longer includes recovery-era package imports.
- Archived tests are retained for historical reference but excluded from active CI.

## `tests/scan/` -> `tests/archive/scan/`

Archived during Prompt 4 (2026-03-02) after `tagslut/scan` implementation was
moved to `legacy/tagslut_scan/` and replaced by a deprecation import stub.

Rationale:
- `scan` is retired from the top-level canonical CLI surface.
- Scanner implementation is preserved under `legacy/` for traceability.
- Archived tests are retained for historical reference but excluded from active CI.
