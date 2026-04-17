# CODEX_BOOTSTRAP_REPORT.md

## tagslut bootstrap: current implemented state

Read only what is needed for the task. Do not preload historical planning material.

## What Codex has already landed

Recent implemented work includes:

- retirement of the `dedupe` alias: `tagslut` is the canonical CLI surface
- targeted lint/type cleanup in the transcoder path
- env-path typing cleanup and legacy env alias warning coverage
- Phase 2 classification seam only, without full classification logic
- v3 database migration `0006` and verification path
- exclusion of one stale v3 migration test that blocked collection
- gig prep workflow documentation, templates, and helper scripts
- key normalization and Camelot mapping utilities
- maintainer helper for syncing stacked Phase 1 PR branches
- Lexicon snapshot import: backup ZIP/main.db support, `locationUnique` path matching, and payload preservation in `track_identity.canonical_payload_json`

## Database work already implemented

Do not describe the database layer as untouched or purely aspirational.

Codex already landed v3 migration `0006`, including:

- new `track_identity` columns:
  - `label`
  - `catalog_number`
  - `canonical_duration_s`
- partial indexes for non-null identity lookups
- composite normalized artist/title index
- v3 migration runner and verification path
- migration tests covering upgrade safety and schema presence

Also note:

- `merged_into_id` intentionally remains `INTEGER REFERENCES track_identity(id)`
- identity-key-based merge-reference migration has not been implemented
- identity service and backfill changes were intentionally left out of `0006`

Treat the DB state as partially advanced, not greenfield.

## Canonical reading order

Read in this order only as needed:

1. `AGENT.md`
2. `README.md`
3. exact file(s) named in the task
4. exact test(s) or failing command
5. `docs/audit/*` only if the task is about repo-vs-doc mismatch
6. storage/v3 files only if the task touches DB, migration, identity, or verification behavior

Do not read broad planning documents unless the task requires them.

## Repository stance

- This is a CLI-first Python repo.
- Preserve existing behavior outside requested scope.
- Prefer minimal, reversible patches.
- Do not perform unrelated cleanup.
- Do not touch databases, artifacts, exports, generated outputs, or external music volumes unless explicitly asked.

## Current reality to preserve

- `tagslut` is the canonical CLI command.
- The live DJ path is staged and explicit.
- Storage/v3 work exists and must not be described as hypothetical.
- Some older planning and audit material is stale relative to current code.
- One outdated v3 migration test was excluded to unblock collection, but that exclusion is not the same thing as full v3 correctness.

## Working rules

- Start from the exact failing command, traceback, file, or test.
- Inspect the smallest relevant file set.
- Prefer targeted pytest runs.
- Do not run the full suite unless explicitly asked.
- Do not invent verification results.

## If the task touches DB or migration behavior

Read only what is directly relevant from:

- `tagslut/storage/`
- `tagslut/storage/v3/`
- `tests/storage/`
- `tests/storage/v3/`

Verify claims against implemented migration code, not against old planning notes.

## If docs and code differ

- Trust `AGENT.md` for current repo doctrine.
- Trust code and merged tests for actual behavior.
- Treat older planning docs as historical unless confirmed by code.
- Update docs only when the task explicitly includes doc correction.

## High-value task routing

### Bug fix
Read:
- failing module
- nearest test
- CLI entrypoint only if relevant

### CLI mismatch
Read:
- `README.md`
- relevant command module
- relevant tests

### DJ pipeline issue
Read only the directly relevant parts of:
- `tagslut/dj/`
- `tagslut/exec/`
- `tests/dj/`
- `tests/exec/`

### DB / identity / migration issue
Read only the directly relevant parts of:
- `tagslut/storage/`
- `tagslut/storage/v3/`
- `tests/storage/`
- `tests/storage/v3/`

## Do not preload

Avoid reading unless explicitly needed:

- session recaps
- task plans
- historical prompts
- backup files
- logs
- broad synthesis documents

## Output expectations

- Be terse.
- Return minimal patch or direct answer.
- No long recap.
- No broad architectural narrative unless explicitly requested.
