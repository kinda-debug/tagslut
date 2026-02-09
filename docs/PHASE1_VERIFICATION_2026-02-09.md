# Phase 1 Verification Report (2026-02-09)

This report closes Phase 1 (`Data Model V3`) from `docs/REDESIGN_TRACKER.md`
with concrete validation evidence.

## Scope Verified

1. V3 schema entities exist and are initialized from `init_db`:
- `asset_file`
- `track_identity`
- `asset_link`
- `provenance_event`
- `move_plan`
- `move_execution`

2. Dual-write plumbing is present and gated:
- `dedupe mgmt register` dual-write path
- move execution scripts (`move_from_plan`, `quarantine_from_plan`)
- env/config gate (`DEDUPE_V3_DUAL_WRITE` / `dedupe.v3.dual_write`)

3. Backfill/parity tooling exists:
- `scripts/backfill_v3_identity_links.py`
- `scripts/backfill_v3_provenance_from_logs.py`
- `scripts/validate_v3_dual_write_parity.py`

## Validation Evidence

Executed on 2026-02-09:

```bash
poetry run python -m py_compile \
  dedupe/storage/v3.py \
  scripts/backfill_v3_identity_links.py \
  scripts/backfill_v3_provenance_from_logs.py \
  scripts/validate_v3_dual_write_parity.py
```

Result: success.

```bash
poetry run flake8 \
  dedupe/storage/v3.py \
  scripts/backfill_v3_identity_links.py \
  scripts/backfill_v3_provenance_from_logs.py \
  scripts/validate_v3_dual_write_parity.py \
  tests/test_v3_phase1_helpers.py \
  tests/test_v3_phase1_scripts.py \
  tests/test_move_from_plan_dual_write.py
```

Result: success.

```bash
poetry run pytest -q \
  tests/test_v3_phase1_helpers.py \
  tests/test_v3_phase1_scripts.py \
  tests/test_move_from_plan_dual_write.py
```

Result: `7 passed`.

```bash
poetry run pytest -q \
  tests/test_move_exec_compat.py \
  tests/test_repo_layout_audit_script.py \
  tests/test_cli_docs_consistency_script.py \
  tests/test_cli_transitional_warnings.py \
  tests/test_repo_structure.py
```

Result: `21 passed`.

## Runbook Link

Operational instructions for enabling, backfilling, and validating V3 dual-write
remain in:

- `docs/PHASE1_V3_DUAL_WRITE.md`

## Closure

Phase 1 is complete from a code + verification baseline perspective. Phase 2
(`Policy Engine`) can proceed.
