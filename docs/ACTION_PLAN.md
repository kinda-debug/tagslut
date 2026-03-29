# tagslut — Action Plan

<!-- Status: Active. This is the canonical execution queue. -->
<!-- Source of truth for sequencing: this file. -->
<!-- Stream status lives in docs/REDESIGN_TRACKER.md. Historical task assignment context lives in docs/ROADMAP.md. -->

## How to use this file

Use this file for one question only:

**What do we do next, in what order?**

Do not use `docs/ROADMAP.md`, `docs/PROGRESS_REPORT.md`, `docs/PHASE1_STATUS.md`, or dated technical state reports as the live execution queue.

## Current control-doc ownership

| Question | Canonical file |
| --- | --- |
| What do we do next? | `docs/ACTION_PLAN.md` |
| Which redesign streams are open or closed? | `docs/REDESIGN_TRACKER.md` |
| Historical task contract / agent assignment | `docs/ROADMAP.md` |
| Wrapper retirement policy and family audit | `docs/SURFACE_POLICY.md` |
| Short human-readable snapshot | `docs/PROGRESS_REPORT.md` |

## Current execution queue

### 1. Legacy wrapper hard removal — intake family decoupling
**Status:** READY  
**Why now:** Wrapper-family planning is complete and the hidden retired recovery family is already removed. The next safe removal stream is the intake wrapper family, but only after internal callers are moved off `tools/get*`.  
**Scope:** move active callers and doc-consistency checks off `tools/get`, `tools/get-intake`, `tools/get-sync`, `tools/get-report`, `tools/get-help`, `tools/get-auto`, `tools/get-all`.  
**Done when:** leaf aliases can be removed in focused PRs without breaking runtime callers or active docs.

### 2. Legacy wrapper hard removal — review wrapper decoupling
**Status:** READY  
**Why after item 1:** Family audit and removal order are documented, but `tagslut execute` and Makefile paths still depend on `tools/review/*`.  
**Scope:** replace shell delegation for `promote-tags` and `quarantine-plan`, then remove the least-coupled review wrappers first.  
**Done when:** no active `tagslut/cli` runtime path shells to legacy review wrappers.

### 3. Provider-repair asymmetry decision
**Status:** NEEDS-DESIGN  
**Why still open:** The redesign queue still lacks an explicit decision on whether non-Beatport duplicate remediation is manual-only or backed by generic tooling.  
**Done when:** architecture and ops docs state the policy clearly enough to unblock any dependent proof-test work.

### Follow-up: staged lint cleanup (by module family)
- Debt-heavy modules are temporarily excluded from CI linting (`tagslut/storage/v3/migrations`, `tagslut/storage/v3/legacy`, `tagslut/storage/v2`). Lint remains enabled for actively touched Python surfaces.
- Stage cleanup by module family, re-enabling lint in CI as each family is cleaned:
  1. `tagslut/storage/v3/migrations`
  2. `tagslut/storage/v3/legacy` and `tagslut/storage/v2`
  3. Remaining `tagslut/storage/v3` submodules (chunked by domain: identity / ingest / reconcile / dj)
  4. CLI + tools

## Recently completed — do not reopen

- Pytest collection blocker for missing `tools.dj_usb_analyzer` import.
- Pool-wizard transcode path fixture-backed proof.
- `process-root` phase contract documentation in `docs/WORKFLOWS.md`.
- Legacy wrapper family audit and staged removal order in `docs/SURFACE_POLICY.md`.
- Hidden retired recovery compatibility family removal.

## Permanent safety rules

- Use only `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db` as the canonical fresh DB path.
- The removed symlink at `/Users/georgeskhawam/Projects/tagslut_db/music_v3.db` must never be recreated.
- Do not touch mounted library volumes in agent implementation PRs unless the task is explicitly operator-only.
- Do not mix multiple wrapper families in the same removal PR.
