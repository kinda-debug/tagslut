# AGENT.md - Repository Operating Guide for tagslut

## Purpose
`tagslut` is a deterministic, auditable music-library management toolkit for large lossless collections.
DJ workflows are optional and downstream: they consume canonical outputs but must not rewrite canonical truth.

Recovery-era work is archived. Active work is forward-looking, deterministic, and verification-gated.

## Branch / Release Topology
- Default/protected branch: `dev`
- There is no `main` branch in this repo topology.
- “Sealed baseline” releases are anchored by annotated tags (e.g. `v3-baseline-YYYY-MM-DD`) pointing to `origin/dev`.

## Documentation Scope and Precedence
This repo has a large markdown surface split into:
- Active docs in `docs/`
- Historical docs in `docs/archive/`
- Tool/package readmes in `tools/`, `legacy/`, and package subfolders

When docs conflict, use this precedence:
1. This file (`AGENT.md`)
2. `docs/OPERATIONS.md`
3. `docs/ARCHITECTURE_V3.md`
4. `docs/WORKFLOWS.md`
5. `docs/SCRIPT_SURFACE.md` and `docs/SURFACE_POLICY.md`
6. `docs/TROUBLESHOOTING.md`
7. `docs/archive/**` (historical reference only)

## Canonical Operational Surface (v3)
Prefer these command groups for new operator-facing work:
1. `tagslut intake`
2. `tagslut index`
3. `tagslut decide`
4. `tagslut execute`
5. `tagslut verify`
6. `tagslut report`

Operator entrypoint for canonical pipeline:
- `python -m tagslut intake process-root`

Phase controls (operator-facing):
- `--scan-only` (register/integrity/hash only)
- `--phases ...` (explicit phases)

Promotion is an explicit phase and is guarded by invariant checks.

DJ workflows:
- Are downstream consumers of `preferred_asset` + `identity_status`.
- Must not modify canonical metadata or promotion semantics.

## Core Data Model (v3) - Concepts
- **asset**: a file on disk tracked as `asset_file`
- **identity**: normalized track entity tracked as `track_identity`
- **link**: `asset_link` maps asset → identity
- **preferred asset**: deterministic canonical asset per identity (`preferred_asset`)
- **lifecycle status**: `identity_status` (active/orphan/archived); merged identities use `merged_into_id`
- **provenance**: auditable events in `provenance_event`

## Core Invariants (Do Not Violate)
1. Master lossless library is the source of truth.
2. Derived libraries (DJ MP3 pools, Rekordbox exports, USB exports) are outputs, not source data.
3. Move workflows are auditable (receipts/logs); never “silent moves”.
4. Integrity/hash/duration gates must be respected before promotion.
5. Prefer deterministic planning/execution (`decide` -> `execute` -> `verify`) where applicable.
6. Keep runtime outputs in `artifacts/` or `output/`, not repository root.
7. **NO PERMANENT REMOVAL**: never permanently delete user files; only move items to Trash when removal is required.

## Hardcoded Path Policy (Strict)
- No hardcoded workstation paths in tracked code or configs:
  - `/Users/...`
  - `/Volumes/...`
  - `tagslut_db/EPOCH...`
- Allowed alternatives:
  - required CLI args
  - environment variables (`TAGSLUT_DB`, `LIBRARY_ROOT`, etc.)
  - placeholders in docs only (e.g. `<V3_DB>`, `<LIBRARY_ROOT>`)
- Local-only config (`.env`, `.vscode/settings.json`) must not be committed unless sanitized templates:
  - use `.env.example`
  - use `.vscode/settings.json.example`

## Safety Gates (Operator-Grade)
When working on core v3 pipelines or promotion semantics, ensure these gates exist and remain green:
- `doctor-v3` checks (foreign keys, required tables, basic counts)
- migration verification checks (v2 -> v3 preservation where applicable)
- promotion invariant checks (preferred asset selection under root)
- identity QA reports (coverage + inconsistency flags)

Preferred operator sequences live in `docs/OPERATIONS.md`.

## DJ Workflow Rule (Downstream-Only)
DJ tooling must:
- select from `identity_status.status='active'` (default) and `preferred_asset`
- store DJ decisions in DJ-only tables (e.g. `dj_track_profile`)
- export/copy/transcode from preferred assets into a separate destination
- never mutate canonical library state

## Repository Ownership Map
- `tagslut/`: package and CLI code (canonical surface)
- `tools/review/`: operational scripts used by `process-root`
- `scripts/`: audits, migrations, verification, DJ utilities
- `config/`: policies, blocklists, workflow configs
- `docs/`: active operator/developer docs
- `docs/archive/`: historical docs only
- `legacy/`: retired code/assets only
- `artifacts/`, `output/`: generated runtime outputs

## Agent Workflow Expectations
Before editing:
1. Read the active docs relevant to the target area (minimum: `docs/OPERATIONS.md`, `docs/ARCHITECTURE_V3.md`).
2. Read the source files implementing the behavior being changed.
3. Confirm command/help behavior directly when changing CLI surface.

During edits:
1. Prefer implementing active logic in `tagslut/` and `tools/review/`.
2. Do not introduce new operator-facing behavior under `legacy/`.
3. Keep DB/schema changes additive and migration-safe.
4. Preserve auditable behavior for file moves, promotions, and exports.
5. Keep PR scope tight: one operational change-set at a time.

After edits (minimum validation set):
1. `poetry run python -m pytest -q`
2. `poetry run python scripts/audit_repo_layout.py`
3. `poetry run python scripts/check_cli_docs_consistency.py`
4. If CLI changed: run relevant `python -m tagslut ... --help` checks
5. If promotion touched: run post-promote invariant check workflow described in `docs/OPERATIONS.md`

## Documentation Update Rules
When behavior or command surface changes, update the matching docs in the same change set:
- `docs/OPERATIONS.md`
- `docs/ARCHITECTURE_V3.md`
- `docs/WORKFLOWS.md`
- `docs/SCRIPT_SURFACE.md` / `docs/SURFACE_POLICY.md` (if surface policy changed)

If a change only affects historical docs, keep it under `docs/archive/` and do not re-promote archived workflows into active docs.

## Practical Safety Notes
- Treat `warn`/`fail` buckets as review queues, not auto-delete signals.
- Rekordbox/Lexicon are downstream consumers; they are not authoritative stores.
- Prefer plan/execute patterns for any workflow that copies/moves/transcodes files.
