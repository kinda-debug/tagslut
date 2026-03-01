# docs/ — Documentation Index

This directory contains the active operator and developer documentation for the `tagslut` package.

## Operator Docs (start here)

- [WORKFLOWS.md](WORKFLOWS.md) — end-to-end operating procedures
- [OPERATIONS.md](OPERATIONS.md) — day-to-day commands and recipes
- [DJ_WORKFLOW.md](DJ_WORKFLOW.md) — DJ pool build and USB sync
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — known issues and fixes

## Architecture

- [ARCHITECTURE.md](ARCHITECTURE.md) — system design, data flow, and provenance model
- [SCRIPT_SURFACE.md](SCRIPT_SURFACE.md) — canonical command map
- [SURFACE_POLICY.md](SURFACE_POLICY.md) — surface governance rules

## Project Status

- [PROJECT.md](PROJECT.md) — project overview and goals
- [PROGRESS_REPORT.md](PROGRESS_REPORT.md) — current state and pending work
- [REDESIGN_TRACKER.md](REDESIGN_TRACKER.md) — v3 program status and decisions log

## DJ Tools

- [DJ_REVIEW_APP.md](DJ_REVIEW_APP.md) — DJ review web app usage and configuration

## Implementation History (reference only)

- [PHASE5_LEGACY_DECOMMISSION.md](PHASE5_LEGACY_DECOMMISSION.md) — Phase 5 runbook (completed)
- [CODEX_PROMPTS.md](CODEX_PROMPTS.md) — Round 1 Codex implementation record
- [CODEX_PROMPTS_ROUND2.md](CODEX_PROMPTS_ROUND2.md) — Round 2 Codex implementation record

## Historical Docs (reference only)

- [SCANNER_V1.md](SCANNER_V1.md) — scanner v1 design reference
- [SCANNER_V1_PROGRESS.md](SCANNER_V1_PROGRESS.md) — scanner v1 progress snapshot
- [IMPLEMENTATION_PLAN_DJ_GIG.md](IMPLEMENTATION_PLAN_DJ_GIG.md) — DJ gig implementation plan
- [IMPLEMENTATION_PLAN_SCANNER_V1.md](IMPLEMENTATION_PLAN_SCANNER_V1.md) — scanner implementation plan
- [TESTS_RETIRED.md](TESTS_RETIRED.md) — retired test inventory and notes

## Audit Notes

### `tagslut_import/` (top-level directory)

**Audit date:** 2026-03

Following a structural audit (see `docs/TAGSLUT_IMPORT.md`), the `tagslut_import/` top-level directory was confirmed **absent** from this repository. It is not an importable package, is not listed in `pyproject.toml`, and has no files or references anywhere in the codebase. No action to restore or create it is required.

## Archive

Historical and retired documents live in `docs/archive/`. See `docs/archive/README.md` for the index.
