# Radical Redesign Proposal - tagslut (2026-02-09)

## Executive Summary

This proposal redesigns tagslut from a script-heavy toolkit into a policy-driven, stateful library operating system for audio assets.

Execution tracker:
- `docs/REDESIGN_TRACKER.md`

Core outcome:
- one canonical data model
- one authoritative decision engine
- one move-only execution engine
- clean CLI surface with stable commands
- strict DJ safety gates (duration hard gate)

The redesign keeps current project philosophy intact: provenance-first, move-only, trusted-source promotion, and explicit separation of DJ-critical vs non-DJ workflows.

## Why Radical Redesign Is Needed

Current pain points:
1. Operational surface fragmentation:
- core behavior split across `tagslut/`, `tools/review/`, and `legacy/` wrappers
- duplicated script intent and mixed maturity levels

2. Documentation/implementation drift:
- command docs and real command behavior diverge over time
- operators cannot infer confidence from docs alone

3. Decision logic spread across stages:
- prefilter, check, scan, fp audit, plan, move are partially duplicated and partially disconnected

4. High-risk path to production moves:
- move-only policy exists, but safety checks and evidence are not centrally enforced by a single execution contract

## Redesign Principles

1. Provenance is first-class data, not log side effects.
2. Every decision is policy-evaluated and audit-stamped.
3. Move operations are centralized behind one execution engine.
4. DJ workflows are strict by default; non-DJ workflows can be permissive by policy.
5. Scripts become thin adapters over stable library APIs.
6. No hard-coded path assumptions; all zones and roots are configuration + policy.

## Target Architecture

### 1. Layered System

1. `tagslut.domain` (new):
- pure domain model (TrackCandidate, LibraryAsset, Decision, MovePlan, PolicyOutcome)
- no IO, no DB calls

2. `tagslut.policy` (new):
- declarative rule engine
- policy profiles (`dj_strict`, `library_balanced`, `bulk_recovery`)

3. `tagslut.store`:
- repository interfaces + SQLite implementation
- migration-managed schema

4. `tagslut.pipeline` (new):
- orchestrates stages as resumable jobs
- event journal per run

5. `tagslut.exec` (new):
- single move-only executor
- preflight + hash verification + atomic move commit

6. `tagslut.adapters`:
- Beatport/Tidal intake adapters
- metadata provider adapters
- legacy script compatibility adapters

### 2. Unified Pipeline Model

Every intake/rebuild run uses a consistent staged pipeline:
1. `discover`
2. `identity`
3. `compare`
4. `decide`
5. `plan`
6. `execute` (optional)
7. `verify`
8. `report`

Each stage emits typed events into a run journal, enabling resume and forensics.

## Canonical Data Model (V3)

### Entities

1. `asset_file`
- immutable snapshot of a file observation (`path`, `size`, `mtime`, hashes, audio tech)

2. `track_identity`
- canonical track identity candidate (ISRC, Beatport ID, normalized artist/title, duration ref)

3. `asset_link`
- many-to-one mapping from observed files to identity candidates with confidence

4. `provenance_event`
- append-only events: discovered, matched, policy_decided, moved, quarantined, promoted, waived

5. `move_plan`
- immutable plan artifact with deterministic content hash and policy version

6. `move_execution`
- execution result rows per planned action with verification details

### Required Invariants

1. Any `promote` action for DJ assets requires `duration_status=ok` unless explicit waiver event exists.
2. Every destructive action must reference an originating `move_plan` and `policy_version`.
3. No file path mutation in DB without a matching `move_execution` success event.

## Policy Engine (Critical)

Policy is stored as versioned YAML (for example `config/policies/dj_strict.yaml`) and loaded by engine.

Rule categories:
1. Identity confidence rules
2. Source trust ranking rules
3. Duration gate rules
4. Format/quality tie-breaker rules
5. Zone routing rules
6. Manual waiver rules

Example decisions:
- `skip_download`
- `allow_download`
- `mark_replace_candidate`
- `promote_to_final`
- `stash_to_fix`
- `quarantine`
- `requires_manual_review`

## CLI Redesign (Stable Surface)

Proposed top-level commands:
1. `tagslut intake`:
- fetch + prefilter + register for external URLs/sources

2. `tagslut index`:
- scan/index local trees and refresh inventory state

3. `tagslut decide`:
- run policy evaluation and generate deterministic plans

4. `tagslut execute`:
- apply move plan through centralized move engine

5. `tagslut verify`:
- verify moved/promoted assets, duration gates, integrity

6. `tagslut report`:
- summarize runs, drift, anomalies, KPIs

7. `tagslut auth`:
- provider auth management

Compatibility strategy:
- keep current commands (`mgmt`, `metadata`, `recover`, `tools/get-intake`) as wrappers to new engine during migration
- deprecate legacy wrappers in phases with explicit warning horizon

## Move-Only Execution Contract

All move actions must pass this contract:
1. Plan action resolved to absolute source and destination.
2. Source existence and hash check preflight.
3. Destination collision policy resolution (`skip`, `replace`, `abort`) via policy.
4. Atomic move operation with post-move verification.
5. Source removal only after destination verification success.
6. Execution event persisted (`move_execution`) before DB path mutation commit.

## DJ vs Non-DJ Separation (First-Class)

### DJ lane (`dj_strict`)
- duration hard gate mandatory
- higher identity confidence threshold
- no auto-promote on ambiguous matches
- quarantine/stash preferred over risky replacement

### Non-DJ lane (`library_balanced`)
- relaxed confidence thresholds
- optional duration warning tolerance
- batch-friendly promotion behavior

Lane assignment inputs:
- explicit operator flag
- source profile
- tag conventions
- policy overrides

## Folder and Zone Strategy

Zones become explicit state machine nodes:
- `inbox`
- `staging`
- `accepted` (final library)
- `fix`
- `quarantine`
- `archive`

Path templates are policy-driven and centralized (no script-local path logic).

## Observability and Auditability

Each run produces:
1. run manifest JSON (`run_id`, policy version, command, roots)
2. append-only event journal JSONL
3. plan artifact(s) with content hashes
4. execution receipts with before/after path and verification details
5. operator-facing summary report

Key dashboards/metrics:
- duplicate avoidance rate pre-download
- promotion success rate
- DJ duration gate failure count
- manual review backlog size
- move rollback incidence

## Migration Plan

### Phase 0 - Stabilize Surface (1-2 weeks)
1. freeze new legacy wrapper additions
2. make docs reference only canonical entrypoints
3. add warning banners on transitional commands

### Phase 1 - Data Model V3 (2-3 weeks)
1. add new tables/entities
2. dual-write from current workflows
3. backfill identity/provenance links from existing DB

### Phase 2 - Policy + Decide Engine (2-4 weeks)
1. implement policy loader and evaluator
2. port current heuristics into policy rules
3. produce deterministic move plans with policy stamps

### Phase 3 - Central Move Executor (2-3 weeks)
1. route `move_from_plan` and related flows through executor API
2. enforce move-only execution contract globally
3. add receipt verification and fail-safe rollback hooks

### Phase 4 - CLI Convergence (2-3 weeks)
1. introduce `intake/index/decide/execute/verify/report` commands
2. keep wrappers with deprecation warnings
3. remove direct script dependencies from standard operator flow

### Phase 5 - Decommission Legacy Paths (after burn-in)
1. archive legacy wrappers
2. lock script surface to canonical adapters only
3. freeze schema and policy contract for v3

## Risks and Mitigations

1. Migration complexity:
- mitigate with dual-write and staged cutover

2. Operator disruption:
- mitigate with compatibility wrappers and identical output artifacts during transition

3. Policy misconfiguration:
- mitigate with policy linting, dry-run previews, and required approval for DJ waiver policies

4. Performance regression:
- mitigate with incremental indexing, caching, and worker pools per stage

## Success Criteria

1. 90% of routine ops run through canonical CLI without direct script calls.
2. zero untracked path mutations in DB.
3. zero DJ promotions with `duration_status != ok` without waiver.
4. reproducible run outputs (same inputs + same policy -> same plan hash).
5. documented deprecation of transitional wrappers with dated timeline.

## Immediate Next Steps (Actionable)

1. Approve this target architecture and migration phases.
2. Maintain `docs/REDESIGN_TRACKER.md` with owners, milestones, and weekly status.
3. Implement Phase 0 and Phase 1 skeleton in a feature branch:
- new v3 schema tables
- run journal scaffolding
- policy loader stub
4. Route `tools/get-intake` planning output through provisional `tagslut.decide` API while preserving current behavior.

## Appendix A - Proposed Mapping From Current Surface

Current -> Target:
1. `tools/get-intake` -> `tagslut intake`
2. `tagslut mgmt register/check/...` -> `tagslut index` + `tagslut decide`
3. `tools/review/plan_*` -> `tagslut decide --plan-type ...`
4. `tools/review/move_from_plan.py` -> `tagslut execute --plan <plan.csv|json>`
5. `tagslut recover` -> `tagslut verify` + `tagslut repair` (optional future split)

## Appendix B - Non-Goals In First Redesign Wave

1. Replacing bpdl/tiddl binaries.
2. Building a GUI before CLI convergence.
3. Perfect global metadata normalization in one pass.
4. Forcing retrospective full-library retag before migration.
