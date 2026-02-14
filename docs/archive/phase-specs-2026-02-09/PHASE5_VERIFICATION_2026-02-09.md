# Phase 5 Verification Report (2026-02-09)

This report closes Phase 5 (`Legacy Decommission`) in:
- `docs/REDESIGN_TRACKER.md`

## Scope Verified

1. Removed legacy top-level wrappers:
- `scan`, `recommend`, `apply`, `promote`, `quarantine`

2. Removed compatibility wrappers from top-level surface:
- `mgmt`, `metadata`, `recover`

3. Canonical command groups remain available:
- `intake/index/decide/execute/verify/report/auth`

4. Docs and audit checks reflect the decommissioned surface.

## Validation Evidence

Executed on February 9, 2026:

```bash
python -m dedupe --help
```

Result: top-level wrapper commands are absent; canonical groups are present.

```bash
poetry run python scripts/check_cli_docs_consistency.py
poetry run python scripts/audit_repo_layout.py
```

Result: pass.

```bash
poetry run pytest -q \
  tests/test_phase4_cli_surface.py \
  tests/test_cli_transitional_warnings.py \
  tests/test_cli_docs_consistency_script.py \
  tests/test_repo_layout_audit_script.py
```

Result: passing.

## Runbook Link

- `docs/PHASE5_LEGACY_DECOMMISSION.md`

## Closure

Phase 5 decommission is complete. The v3 CLI surface is stable on:
- `dedupe intake`
- `dedupe index`
- `dedupe decide`
- `dedupe execute`
- `dedupe verify`
- `dedupe report`
- `dedupe auth`
