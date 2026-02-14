# Phase 5 - Legacy Decommission Plan (2026-02-09)

This document is the execution plan for Phase 5 (`Legacy Decommission`) from:
- `docs/REDESIGN_TRACKER.md`

## Scope

1. Archive/remove legacy transitional wrappers:
- `dedupe scan`
- `dedupe recommend`
- `dedupe apply`
- `dedupe promote`
- `dedupe quarantine ...`

2. Retire compatibility wrappers:
- `dedupe mgmt ...`
- `dedupe metadata ...`
- `dedupe recover ...`

## Execution Status (as of February 9, 2026)

1. Legacy wrapper command removal from `dedupe` top-level CLI: completed.
2. Compatibility wrapper retirement (`mgmt/metadata/recover`): completed.

## Ticket Board

### Transitional Wrapper Decommission Tickets

| Ticket | Wrapper | Canonical Replacement | Status | Target Date |
|---|---|---|---|---|
| `P5-LEG-001` | `dedupe scan` | `dedupe index ...` and `dedupe verify ...` | Completed (2026-02-09) | June 15, 2026 |
| `P5-LEG-002` | `dedupe recommend` | `dedupe decide plan ...` | Completed (2026-02-09) | June 15, 2026 |
| `P5-LEG-003` | `dedupe apply` | `dedupe execute move-plan ...` | Completed (2026-02-09) | June 15, 2026 |
| `P5-LEG-004` | `dedupe promote` | `dedupe execute promote-tags ...` | Completed (2026-02-09) | June 15, 2026 |
| `P5-LEG-005` | `dedupe quarantine ...` | `dedupe execute quarantine-plan ...` | Completed (2026-02-09) | June 15, 2026 |

### Compatibility Wrapper Retirement Tickets

| Ticket | Wrapper | Canonical Replacement | Status | Target Date |
|---|---|---|---|---|
| `P5-COMP-001` | `dedupe mgmt ...` | `dedupe index ...` + `dedupe report m3u ...` | Completed (2026-02-09) | July 3, 2026 |
| `P5-COMP-002` | `dedupe metadata ...` | `dedupe auth ...` + `dedupe index enrich ...` | Completed (2026-02-09) | July 3, 2026 |
| `P5-COMP-003` | `dedupe recover ...` | `dedupe verify recovery ...` + `dedupe report recovery ...` | Completed (2026-02-09) | July 3, 2026 |

## Removal Gates

These gates were satisfied before deleting compatibility wrappers in `dedupe/cli/main.py`.

### Gate A - Coverage Parity

1. Canonical replacement command exists and is operator-documented.
2. Wrapper behavior has a tested equivalent path in canonical flow.
3. No active runbook requires the wrapper as the only supported path.

### Gate B - Usage Burn-In

1. Wrapper has no operational dependency in `README.md`, `docs/SCRIPT_SURFACE.md`, and `docs/SURFACE_POLICY.md`.
2. Weekly operator review confirms no blocking workflows for that wrapper class.
3. A deprecation notice window has elapsed (minimum 30 days from warning start).

### Gate C - Safety/Verification

1. `poetry run python scripts/check_cli_docs_consistency.py` passes.
2. `poetry run python scripts/audit_repo_layout.py` passes.
3. Critical regression tests for `decide/execute/verify/report` pass.
4. DJ duration gate policy remains enforced (`duration_status=ok` unless waiver event exists).

## Timeline

1. **Phase 5 kickoff** - June 1, 2026
- Confirm owners for each `P5-*` ticket.
- Freeze any new transitional wrapper additions.

2. **Legacy transitional wrappers archive window** - June 1 to June 15, 2026
- Complete `P5-LEG-001` to `P5-LEG-005`.
- Remove wrapper references from operator docs.
  - Status: completed early on February 9, 2026.

3. **Compatibility wrappers burn-in close** - June 16 to July 3, 2026
- Complete `P5-COMP-001` to `P5-COMP-003`.
- Remove `mgmt/metadata/recover` after final gate review.
  - Status: completed early on February 9, 2026.

4. **Phase 5 close** - July 3, 2026
- Declare v3 CLI surface stable.
- Publish Phase 5 verification report.

## Rollback Policy

If a wrapper removal blocks production workflows:
1. Restore wrapper in a hotfix commit.
2. Add explicit blocker note to `docs/REDESIGN_TRACKER.md`.
3. Re-open corresponding `P5-*` ticket with root-cause + retargeted date.
