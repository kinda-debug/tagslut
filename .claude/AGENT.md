# AGENT.md - Repository Operating Guide for tagslut

## Purpose
`tagslut` is a music-library management toolkit for large FLAC collections with DJ-oriented workflows.
Recovery-era work is archived; active work is forward-looking, deterministic, and auditable.

## Documentation Scope and Precedence
This repo has a large markdown surface. The tracked markdown set currently splits roughly into:
- Active docs in `docs/` (operator and implementation guidance)
- Historical docs in `docs/archive/`
- Tool/package readmes in `tools/`, `legacy/`, and package subfolders

When docs conflict, use this precedence:
1. This file (`AGENT.md`)
2. `REPORT.md`
3. `docs/WORKFLOWS.md` and `docs/OPERATIONS.md`
4. `docs/SCRIPT_SURFACE.md` and `docs/SURFACE_POLICY.md`
5. `docs/TROUBLESHOOTING.md`
6. `docs/archive/**` (historical reference only)

## Canonical Operational Surface
Prefer these command groups for new operator-facing work:
1. `tagslut intake`
2. `tagslut index`
3. `tagslut decide`
4. `tagslut execute`
5. `tagslut verify`
6. `tagslut report`
7. `tagslut auth`

Also active in the current CLI surface (specialized use):
- `tagslut export`
- `tagslut dj`
- `tagslut gig`
- `tagslut canonize`
- `tagslut enrich-file`
- `tagslut show-zone`
- `tagslut explain-keeper`
- `tagslut recovery` (currently a stub path; treat as limited)

Branding and alias policy:
- `tagslut` is the preferred command brand.
- `dedupe` is a deprecated compatibility alias and is scheduled for removal on **2026-06-01**.

Retired wrappers for new work:
- `scan`, `recommend`, `apply`, `promote`, `quarantine`, `mgmt`, `metadata`, `recover`

## Core Invariants
1. Master FLAC library is the source of truth.
2. DJ MP3 pools are derived outputs, not source data.
3. Move workflows are move-only and auditable (receipts/logs).
4. Integrity and duration gates must be respected before promotion.
5. Prefer deterministic planning/execution (`decide` -> `execute` -> `verify`).
6. Keep runtime outputs in `artifacts/`, not repository root.
7. **NO PERMANENT REMOVAL**: never permanently delete files or folders, even if asked; only move items to Trash.

## Repository Ownership Map
- `tagslut/`: productized package and CLI code
- `tools/review/`: active operational scripts
- `scripts/`: maintenance, audits, migrations, batch helpers
- `config/`: policies, blocklists, workflow configs
- `docs/`: active operator/developer docs
- `docs/archive/`: historical docs only (do not treat as active policy)
- `legacy/`: retired code and historical assets only
- `artifacts/`, `output/`: generated runtime outputs

## Agent Workflow Expectations
Before editing:
1. Read the active docs relevant to the target area (at minimum from `docs/`).
2. Read the source files that implement the behavior being changed.
3. Confirm command/help behavior directly when changing CLI surface.

During edits:
1. Prefer `tagslut/` and `tools/review/` for active logic.
2. Do not introduce new operator-facing behavior under `legacy/`.
3. Keep DB/schema changes additive and migration-safe.
4. Preserve auditable behavior for file moves and promotions.

## Operator Interaction Preferences
1. Do not run long scripts in the background (`&`, `nohup`, detached sessions, or similar).
2. Keep long-running commands in the foreground so output is visible while they run.
3. Keep the operator in the loop before running heavyweight commands.
4. Use verbose mode by default for scripts/commands when supported (`--verbose`, `-v`, `-vv`).
5. Avoid silent execution patterns unless explicitly requested.
6. If the operator asks to remove/delete something, send it to Trash instead of permanently deleting it.

After edits (minimum validation set):
1. `poetry run pytest -q`
2. `poetry run python scripts/audit_repo_layout.py`
3. `poetry run python scripts/check_cli_docs_consistency.py`
4. If CLI changed: run relevant `tagslut <group> --help` checks

## Documentation Update Rules
When behavior or command surface changes, update the matching docs in the same change set:
- `docs/WORKFLOWS.md`
- `docs/OPERATIONS.md`
- `docs/SCRIPT_SURFACE.md`
- `docs/SURFACE_POLICY.md`
- `REPORT.md` (if strategy/positioning changes)

If a change only affects historical docs, keep it under `docs/archive/` and do not re-promote archived workflows into active docs.

## Practical Safety Notes
- Pre-download check should be the default posture before downloads.
- Provider defaults in active workflows are typically Beatport/Tidal unless explicitly overridden.
- Treat `warn`/`fail` duration buckets as review queues, not auto-delete signals.
- Rekordbox/Lexicon are downstream consumers; they are not authoritative source-of-truth stores.
