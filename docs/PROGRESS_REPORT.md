<!-- Status: Active derived summary. Keep this file short. -->
<!-- Source of truth: docs/ACTION_PLAN.md for execution order; docs/REDESIGN_TRACKER.md for open/closed streams; docs/ROADMAP.md for historical task contract. -->

# Progress Report

Report date: March 25, 2026

## How to use this file

This file is a one-screen snapshot only.

- Use `docs/ACTION_PLAN.md` for the current execution queue.
- Use `docs/REDESIGN_TRACKER.md` for redesign stream status.
- Use `docs/ROADMAP.md` for historical task ownership and agent contract context.
- Do not use this file as the canonical backlog.

## Current snapshot

### Completed since the March 23 report

- Pytest collection blocker cleared: the missing `tools.dj_usb_analyzer` import issue is no longer the active top blocker.
- Pool-wizard transcode path now has a fixture-backed proof covering plan, execute, artifacts, final MP3 output, and disposable DB writes.
- `WORKFLOWS.md` now documents concise `process-root` phase contracts for `identify`, `enrich`, `art`, `promote`, and `dj`.
- Legacy wrapper hard-removal planning now lives in `docs/SURFACE_POLICY.md` as a wrapper-family audit with ordered removal sequencing.
- The hidden retired recovery compatibility family has been removed from the active CLI surface.

### Current top priorities

1. Legacy wrapper hard removal: intake wrapper family decoupling (`tools/get*`) before deletion.
2. Legacy wrapper hard removal: review-wrapper decoupling (`tools/review/*`) before deletion.
3. Remaining design/doc work from the action queue that is not already represented by the completed streams above.

## Control-doc ownership

| Question | Canonical file |
| --- | --- |
| What do we do next? | `docs/ACTION_PLAN.md` |
| Which redesign streams are open or closed? | `docs/REDESIGN_TRACKER.md` |
| What is historical task assignment context? | `docs/ROADMAP.md` |
| What is current wrapper/surface policy? | `docs/SURFACE_POLICY.md` |
| What is this file for? | A short derived summary only |

## Historical note

Detailed session-by-session logs before this cleanup remain available in Git history.
New work should not expand this file back into a duplicate roadmap.
