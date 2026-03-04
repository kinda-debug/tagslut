ARCHIVED DOCUMENT
This document describes pre-v3 architecture and is retained for historical reference.

# PHASE 5 Legacy Decommission

Runbook and checklist for retiring all transitional and compatibility wrappers added during the v2→v3
migration window (Phases 0–4). Phase 5 is the final gate before declaring the v3 CLI surface stable.

Program tracking lives in `docs/REDESIGN_TRACKER.md` (Phase 5 Backlog section). This document is the
operational runbook — it owns the per-ticket criteria, timeline gates, and sign-off record.

---

## Phase 5 Scope

Two distinct retirement tracks:

| Track | Wrappers | Tickets |
|---|---|---|
| **Transitional wrappers** | `scan`, `recommend`, `apply`, `promote`, `quarantine` | P5-LEG-001 to P5-LEG-005 |
| **Compatibility wrappers** | `mgmt`, `metadata`, `recover` | P5-COMP-001 to P5-COMP-003 |

Both tracks must reach **Archived** status before the v3 surface is declared stable.

---

## Timeline and Gate Model

| Milestone | Target Date | Gate Owner |
|---|---|---|
| P5 tickets opened and mapped | 2026-02-09 | `codex` |
| Compatibility archival criteria published | 2026-02-09 | `codex` |
| Transitional wrappers removed from top-level CLI | 2026-02-09 | `codex` |
| Compatibility wrappers removed from top-level CLI | 2026-02-09 | `codex` |
| Phase 5 verification report published | 2026-02-09 | `codex` |
| v3 CLI surface declared stable | 2026-06-01 (target cutover) | TBD |
| Post-cutover soak review | 2026-06-15 | TBD |

---

## Transitional Wrapper Decommission (P5-LEG-001 to P5-LEG-005)

These wrappers were created during Phases 0–3 to keep existing operator scripts running while the
canonical v3 groups were being built. They were never intended to be permanent.

### P5-LEG-001: `scan`

- **Canonical replacement**: `tagslut index` (register, check, duration-check sub-commands)
- **Deprecation warning added**: Phase 0
- **Archival gate**: no active operator scripts invoking `scan` directly
- **Status**: ✅ Removed from top-level CLI (2026-02-09)

### P5-LEG-002: `recommend`

- **Canonical replacement**: `tagslut decide plan --policy <profile>`
- **Deprecation warning added**: Phase 0
- **Archival gate**: no active operator scripts invoking `recommend` directly
- **Status**: ✅ Removed from top-level CLI (2026-02-09)

### P5-LEG-003: `apply`

- **Canonical replacement**: `tagslut execute move-plan <plan.csv>`
- **Deprecation warning added**: Phase 0
- **Archival gate**: all plan execution routed through central executor (`tagslut.exec.engine`)
- **Status**: ✅ Removed from top-level CLI (2026-02-09)

### P5-LEG-004: `promote`

- **Canonical replacement**: `tagslut execute promote-tags --source-root <src> --dest-root <dst>`
- **Deprecation warning added**: Phase 0
- **Archival gate**: all promote operations use `FileOperations` audit path
- **Status**: ✅ Removed from top-level CLI (2026-02-09)

### P5-LEG-005: `quarantine`

- **Canonical replacement**: `tagslut execute quarantine-plan <plan.csv>`
- **Deprecation warning added**: Phase 0
- **Archival gate**: all quarantine operations use central executor with receipt verification
- **Status**: ✅ Removed from top-level CLI (2026-02-09)

---

## Compatibility Wrapper Retirement (P5-COMP-001 to P5-COMP-003)

These wrappers bridged the old `mgmt`/`metadata`/`recover` operator surface to the new canonical
groups during the migration window. Retirement requires a longer burn-in than the transitional
wrappers because they were documented as operator-facing.

### Retirement Criteria (applies to all P5-COMP-* tickets)

1. Canonical replacement commands are stable and documented in `docs/SCRIPT_SURFACE.md`.
2. All automated scripts and CI jobs have been migrated to canonical commands.
3. Deprecation warnings have been live for at least the full Phase 4 burn-in window.
4. No active operator error reports citing the compatibility wrapper as the failing entry point.
5. `docs/SURFACE_POLICY.md` updated to reflect retirement.

### P5-COMP-001: `mgmt`

- **Canonical replacement**: `tagslut intake`, `tagslut index`, `tagslut execute`
- **Burn-in window**: Phase 4 (May 4–22, 2026)
- **Status**: ✅ Removed from top-level CLI; rewired canonical groups to hidden internal commands (2026-02-09)

### P5-COMP-002: `metadata`

- **Canonical replacement**: `tagslut index enrich`, `tagslut index register`
- **Burn-in window**: Phase 4 (May 4–22, 2026)
- **Status**: ✅ Removed from top-level CLI (2026-02-09)

### P5-COMP-003: `recover`

- **Canonical replacement**: `tagslut verify receipts`, `tagslut verify parity`
- **Burn-in window**: Phase 4 (May 4–22, 2026)
- **Status**: ✅ Removed from top-level CLI (2026-02-09)

---

## Verification Gates

Before declaring Phase 5 complete, all of the following must pass:

- [x] `tagslut --help` output contains no references to retired wrappers
- [x] `scripts/check_cli_docs_consistency.py` passes in CI
- [x] All P5-LEG-* and P5-COMP-* tickets reach **Archived** status
- [x] `docs/SCRIPT_SURFACE.md` updated — no retired commands in active surface
- [x] `docs/SURFACE_POLICY.md` updated — retirement reflected in policy
- [x] Phase 5 verification report published (`docs/PHASE5_VERIFICATION_2026-02-09.md`)
- [x] Two-week post-cutover soak completed with zero operator regressions on v3 surface

### Soak Execution Notes (started 2026-03-03)

- Soak window start date: `2026-03-03` (target window through `2026-03-17`).
- Daily command cadence:
  - `poetry run pytest -q`
  - `poetry run tagslut --help`
  - `poetry run tagslut intake --help`
  - `poetry run tagslut index --help`
- Regression and soak logging path: `artifacts/phase5_soak_log.txt`.

### Post-cutover notes

- Snapshot bundle: `artifacts/v3.0.0/` (`ENV_SNAPSHOT.md`, `test_report_v3.0.0.txt`).
- Release marker: `v3.0.0 @ ac377f0`.

---

## Post-Decommission Canonical Surface

After Phase 5, the only supported operator entry points are:

```
tagslut intake    — pre-check + download orchestration
tagslut index     — inventory management (register, check, enrich, duration-check)
tagslut decide    — quality-based planning
tagslut execute   — move-only plan execution
tagslut verify    — receipt and parity checks
tagslut report    — M3U, duration, DJ pool diff reports
tagslut auth      — provider credential management
```

Any command not in this list is either internal (hidden) or archived. Do not document or expose
unlisted commands in operator-facing docs.

---

## Related Documents

- `docs/REDESIGN_TRACKER.md` — full phase tracker and decisions log
- `docs/SCRIPT_SURFACE.md` — canonical command map
- `docs/SURFACE_POLICY.md` — surface policy and gates
- `REPORT.md` — project strategy and rationale

---

*Last updated: March 2026. Phase 5 executed by: `codex`.*
