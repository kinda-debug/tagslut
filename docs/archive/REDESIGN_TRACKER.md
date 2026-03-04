ARCHIVED DOCUMENT
This document describes pre-v3 architecture and is retained for historical reference.

# Redesign Tracker - tagslut V3 (2026-02-09)

## Scope

Execution tracker for the radical redesign documented in:
- `docs/PROPOSAL_RADICAL_REDESIGN_2026-02-09.md`

This tracker is the working control plane for milestones, ownership, acceptance criteria, and migration safety.

## Program Status

- Start date: February 9, 2026
- Current phase: Phase 5 (Legacy Decommission) - completed
- Program status: phase_5_complete
- Target cutover window: June 2026

## Owners

- Program owner: `TBD`
- Technical lead: `TBD`
- Data model lead: `TBD`
- Policy engine lead: `TBD`
- CLI convergence lead: `TBD`
- Ops validation lead: `TBD`

## Milestones

| Phase | Window (target) | Status | Primary Objective | Exit Criteria |
|---|---|---|---|---|
| Phase 0 - Stabilize Surface | Feb 9, 2026 - Feb 20, 2026 | Completed | Freeze surface drift and align docs with canonical commands | Canonical entrypoint docs updated; new legacy wrappers blocked; deprecation warnings defined |
| Phase 1 - Data Model V3 | Feb 23, 2026 - Mar 13, 2026 | Completed | Add v3 entities and dual-write plumbing | New schema migrated; dual-write enabled for selected flows; backfill job validated |
| Phase 2 - Policy + Decide Engine | Mar 16, 2026 - Apr 10, 2026 | Completed | Implement policy evaluator and deterministic planning | Policy loader live; plan generation policy-stamped; golden test plans stable |
| Phase 3 - Central Move Executor | Apr 13, 2026 - May 1, 2026 | Completed | Route moves through one execution contract | All plan executions use central executor; receipt verification enabled; DB mutation contract enforced |
| Phase 4 - CLI Convergence | May 4, 2026 - May 22, 2026 | Completed | Ship new stable command surface | `intake/index/decide/execute/verify/report/auth` available; wrappers mapped; docs switched |
| Phase 5 - Legacy Decommission | Jun 1, 2026 - Jul 3, 2026 | Completed | Remove transitional dependencies | Legacy wrappers archived; deprecation windows honored; v3 surface declared stable |

## Phase 0 Backlog (Active)

1. Canonical command docs and warning banners
- [x] Add deprecation banner text to transitional commands (`scan`, `recommend`, `apply`, `promote`, `quarantine`)
- [x] Ensure legacy mgmt/recovery workflow docs were archived out of active surface
- [x] Ensure `README.md` only advertises canonical operator flow
- [x] Add CLI/docs consistency checks in CI (`scripts/check_cli_docs_consistency.py`)
- Definition of done: docs and command help are consistent in CI checks

2. Script surface control
- [x] Enforce `docs/SCRIPT_SURFACE.md` as source of truth
- [x] Add CI check to fail on new `legacy/tools` command wrappers without approval tag
- [x] Add CI check for root artifact leakage (logs/csv/db/tmp)
- Definition of done: pull requests fail on surface drift violations

3. Move-only enforcement baseline
- [x] Audit active move scripts for centralized execution hooks
- [x] Define temporary compatibility adapter contract for `tools/review/move_from_plan.py`
- Definition of done: no move path bypasses audit log + verification step

## Phase 1 Backlog (Prepared)

1. Schema additions
- [x] Add `asset_file`
- [x] Add `track_identity`
- [x] Add `asset_link`
- [x] Add `provenance_event`
- [x] Add `move_plan`
- [x] Add `move_execution`

2. Dual-write
- [x] Implement dual-write from existing register/plan/execute flows
- [x] Gate dual-write behind config flag: `tagslut.v3.dual_write=true`
- [x] Add migration validation script for row parity checks

3. Backfill
- [x] Build one-shot backfill for identities from existing DB fields (ISRC/Beatport IDs/tags)
- [x] Build provenance reconstruction for previous move logs under `artifacts/`

## Phase 2 Backlog (Completed)

1. Policy loader and profile definitions
- [x] Implement `tagslut.policy` package with profile models and loader
- [x] Add policy lint rules and lint script (`scripts/lint_policy_profiles.py`)
- [x] Add baseline policy profiles (`dj_strict`, `library_balanced`, `bulk_recovery`)

2. Deterministic decide planner
- [x] Implement deterministic planning API (`tagslut.decide`)
- [x] Stamp plans with `policy.version`, `policy.hash`, and deterministic `run_id`
- [x] Ensure same input + same policy yields same `plan_hash`

3. Validation
- [x] Add golden snapshot hash tests for baseline profiles
- [x] Add policy lint script test coverage
- [x] Publish Phase 2 runbook + verification report

## Phase 3 Backlog (Completed)

1. Central executor
- [x] Add `tagslut.exec.engine` with structured `MoveReceipt`
- [x] Add verification hook (`verify_receipt`) and stable receipt hashing
- [x] Keep compatibility adapter (`tagslut.exec.compat`) mapped to central executor

2. Receipt + mutation contract
- [x] Add `record_move_receipt(...)` for `move_execution` and provenance journaling
- [x] Enforce legacy path mutation via `update_legacy_path_with_receipt(...)`
- [x] Require successful moved receipt before `files.path` mutation

3. Workflow adoption + validation
- [x] Route `move_from_plan` and `quarantine_from_plan` through central executor
- [x] Add Phase 3 executor tests (unit + integration)
- [x] Publish Phase 3 runbook + verification report

## Phase 4 Backlog (Completed)

1. Canonical command group convergence
- [x] Add top-level groups: `intake/index/decide/execute/verify/report/auth`
- [x] Add wrapper bridge commands that map canonical groups to existing operational tooling
- [x] Keep compatibility wrappers (`mgmt/metadata/recover`) functional during migration window

2. Compatibility + migration messaging
- [x] Add explicit deprecation guidance for compatibility wrappers
- [x] Tag internal wrapper invocations to suppress recursive warnings
- [x] Preserve legacy wrappers (`scan/recommend/apply/promote/quarantine`) for burn-in

3. Validation + documentation
- [x] Update `docs/SCRIPT_SURFACE.md` and `docs/SURFACE_POLICY.md` to new canonical surface
- [x] Add Phase 4 runbook and verification report
- [x] Add CLI/docs consistency assertions for converged command groups

## Phase 5 Backlog (Active)

1. Transitional wrapper decommission tickets
- [x] Open ticket set for `scan/recommend/apply/promote/quarantine` (`P5-LEG-001` to `P5-LEG-005`)
- [x] Map each ticket to canonical replacement flow
- [x] Archive wrappers after gate review window closes

2. Compatibility wrapper retirement criteria
- [x] Define archival/removal criteria for `mgmt/metadata/recover`
- [x] Define dated timeline and gate model in `docs/PHASE5_LEGACY_DECOMMISSION.md`
- [x] Execute burn-in closeout and remove wrappers (`P5-COMP-001` to `P5-COMP-003`)

3. Phase 5 verification and handover
- [x] Add Phase 5 verification report with gate evidence
- [x] Update canonical docs to remove transitional wrapper references
- [x] Declare v3 CLI surface stable

## Deliverables By Phase

### Phase 0 Deliverables
- `docs/SURFACE_POLICY.md` (new)
- `docs/MOVE_EXECUTOR_COMPAT.md` (new)
- command deprecation banner implementation
- CI rule set: surface drift, root artifact leakage, doc/help consistency, move-path contract enforcement

### Phase 1 Deliverables
- DB migrations for v3 entities
- repository abstraction scaffolding for v3 writes
- backfill job + verification report
- `docs/PHASE1_V3_DUAL_WRITE.md` runbook
- `docs/PHASE1_VERIFICATION_2026-02-09.md` verification report

### Phase 2 Deliverables
- `tagslut.policy` module
- policy profiles (`dj_strict`, `library_balanced`, `bulk_recovery`)
- deterministic planning API + snapshot tests
- `docs/PHASE2_POLICY_DECIDE.md` runbook
- `docs/PHASE2_VERIFICATION_2026-02-09.md` verification report

### Phase 3 Deliverables
- `tagslut.exec` centralized move executor
- execution receipt schema + verification hooks
- compatibility adapter for existing plan CSV workflows
- `docs/PHASE3_EXECUTOR.md` runbook
- `docs/PHASE3_VERIFICATION_2026-02-09.md` verification report

### Phase 4 Deliverables
- new CLI groups (`intake`, `index`, `decide`, `execute`, `verify`, `report`, `auth`)
- wrappers retained with warnings and clear migration text
- `docs/PHASE4_CLI_CONVERGENCE.md` runbook
- `docs/PHASE4_VERIFICATION_2026-02-09.md` verification report

### Phase 5 Deliverables
- archived transitional wrappers
- stable v3 runbooks and handover docs
- post-cutover review report
- `docs/PHASE5_LEGACY_DECOMMISSION.md` decommission runbook
- `docs/PHASE5_VERIFICATION_2026-02-09.md` verification report

## Quality Gates

1. Safety gates
- [ ] No DJ promotion with `duration_status != ok` unless waiver event exists
- [x] No DB path mutation without matching `move_execution` success receipt

2. Determinism gates
- [x] Same input + same policy version -> same plan content hash
- [x] Plan artifacts stamped with policy version and run id

3. Compatibility gates
- [x] Transitional commands produce migration warning with target command suggestion
- [x] Existing workflows continue to run during migration window

## KPI Baselines and Targets

Baselines (to fill before end of Phase 0):
- duplicate avoidance rate pre-download: `0.00%` (sample baseline from `artifacts/intake_manifest_20260301_154843.json`: `0 skipped / 1 total intent`)
- promotion success rate: `99.52%` (`209 moved / 210 total` in `move_execution`; `1 skip_missing`)
- DJ duration gate fail count per run: `13,761` files currently flagged with `duration_status != 'ok'` out of `21,585` DJ-flagged rows (`is_dj_material=1`)
- manual review backlog: `0` rows with `classification_v2='review'` (current `classification_v2` distribution: `bar=8,732`, `club=8,691`, `remove=6,037`)
- move rollback incidence: `0` explicit rollback rows observed; non-moved execution incidence is `1/210` (`0.48%`, `skip_missing`)

Targets (Phase 4/5):
- >=90% routine operations through canonical v3 commands
- 0 untracked DB path mutations
- 0 unauthorized DJ promotions (duration gate violations)

## Risks and Watchlist

1. Drift between docs and implementation
- Mitigation: command-help snapshot checks in CI

2. Partial migration leaving split-brain execution paths
- Mitigation: explicit compatibility adapter layer and kill switch flags

3. Policy misconfiguration for DJ lane
- Mitigation: policy linting + required approver workflow for waiver rules

4. Runtime overhead from dual-write and event journaling
- Mitigation: profiling budget and worker tuning per stage

## Weekly Cadence

- Weekly review: Mondays
- Update fields each week:
  - phase status
  - completed backlog items
  - blocked items and owner
  - KPI delta
  - risk changes

## Decisions Log

| Date | Decision | Rationale | Owner |
|---|---|---|---|
| 2026-02-09 | Tracker created and Phase 0 opened | Convert proposal into executable program controls | `TBD` |
| 2026-02-09 | Transitional CLI wrappers now emit deprecation warnings; surface policy doc added | Start Phase 0 migration pressure without breaking compatibility | `TBD` |
| 2026-02-09 | Added CI audit step and legacy-wrapper import allowlist guard | Prevent silent surface drift while migration is in progress | `TBD` |
| 2026-02-09 | MGMT mode doc flag drift removed; audit markers tightened to exact stale signatures | Remove false-positive warnings and keep audit actionable | `TBD` |
| 2026-02-09 | Added CLI/docs consistency audit script and CI gate | Enforce canonical docs/help alignment during migration | `TBD` |
| 2026-02-09 | Added `tagslut.exec.compat` move executor adapter and wired plan-based move scripts through it | Establish centralized move execution contract before full v3 executor rollout | `TBD` |
| 2026-02-09 | Added move audit coverage for `promote_by_tags` through `FileOperations` and enforced it in repo audit checks | Close final Phase 0 move-only baseline gap (verification + audit logging across active move paths) | `TBD` |
| 2026-02-09 | Added Phase 1 v3 schema tables, dual-write hooks, backfill scripts, and parity validator | Complete Data Model V3 foundation before policy engine work | `codex` |
| 2026-02-09 | Published Phase 1 verification report with test/lint/parity evidence and runbook linkage | Close Step 1 with explicit validation evidence before opening Phase 2 work | `codex` |
| 2026-02-09 | Added `tagslut.policy` package, baseline profiles, and `scripts/lint_policy_profiles.py` gate | Establish explicit policy contract before central executor cutover | `codex` |
| 2026-02-09 | Added deterministic `tagslut.decide` planner with golden snapshot hashes and policy stamping | Close Phase 2 deterministic planning exit criteria | `codex` |
| 2026-02-09 | Published Phase 2 runbook + verification report | Close Step 2 with explicit validation evidence before opening Phase 3 work | `codex` |
| 2026-02-09 | Added centralized `tagslut.exec` engine with receipt verification and legacy mutation guard rails | Enforce one execution contract and close DB path mutation safety gap | `codex` |
| 2026-02-09 | Routed plan move executors through central engine + receipt persistence helpers | Complete Phase 3 adoption without breaking existing CSV workflows | `codex` |
| 2026-02-09 | Published Phase 3 runbook + verification report | Close Step 3 with explicit validation evidence before opening Phase 4 work | `codex` |
| 2026-02-09 | Added converged CLI groups (`intake/index/decide/execute/verify/report/auth`) with wrapper mapping to existing flows | Expose one stable operator surface without breaking operational scripts during migration | `codex` |
| 2026-02-09 | Updated script-surface policy/docs and added Phase 4 verification checks/reports | Close Step 4 with explicit command/help/docs alignment evidence before opening Phase 5 work | `codex` |
| 2026-02-09 | Opened Phase 5 ticket board (`P5-LEG-*`, `P5-COMP-*`) for wrapper decommission and compatibility retirement | Convert decommission intent into explicit, trackable execution items | `codex` |
| 2026-02-09 | Published compatibility wrapper archival criteria and dated Phase 5 timeline | Make `mgmt/metadata/recover` removal objective and auditable before cutover | `codex` |
| 2026-02-09 | Archived inactive docs/assets from active `docs/` and repo root; rewired AGENTS/GUIDE/Makefile to canonical CLI only | Remove workflow drift and keep active surface strictly aligned to `intake/index/decide/execute/verify/report/auth` | `codex` |
| 2026-02-09 | Formalized Beatport wrapper split: `tools/get` (sync default), `tools/get-sync`, `tools/get-report`; documented m3u-only auto mode and slug-based naming | Keep Beatport intake behavior simple and predictable while preserving report-only path | `codex` |
| 2026-02-09 | Rebrand initiated: package metadata + CLI aliases (`tagslut`, `taglslut`) with `tagslut` compatibility retained; added rebrand runbook | Move operator-facing brand to tagslut without destabilizing existing automation | `codex` |
| 2026-02-09 | Removed `scan/recommend/apply/promote/quarantine` from top-level CLI and updated canonical surface docs/checks | Execute `P5-LEG-001..005` in one batch while preserving `mgmt/metadata/recover` compatibility window | `codex` |
| 2026-02-09 | Removed `mgmt/metadata/recover` from top-level CLI, rewired canonical groups to hidden internal commands, and published Phase 5 verification report | Complete `P5-COMP-001..003` and close the CLI decommission phase with executable validation evidence | `codex` |
| 2026-02-09 | Added OneTagger operational wrappers (`tools/tag-build`, `tools/tag-run`, `tools/tag`) with DB-driven missing-ISRC batching and run summaries | Reduce metadata enrichment friction to one-command defaults while preserving deterministic artifacts and auditability | `codex` |
| 2026-02-09 | Switched OneTagger flow to ISRC-only writes with iterative unresolved retries (`--max-passes`) | Optimize for aggressive ISRC completion first while deferring non-ISRC metadata enrichment | `codex` |

## Immediate Next Actions

1. Assign owners for all lead roles.
2. Record KPI baselines from last 30 days of available logs/artifacts.
3. Publish post-cutover review report.
4. Track any operator regressions on canonical v3 command surface for two-week soak.
