# REPO_SURFACE.md

## Purpose
This file maps the active code surface so work starts in the right place.
Do not scan the whole repository unless the task explicitly requires it.

## Main code areas

### CLI
- `tagslut/cli/`
- `tagslut/cli/commands/`

Use for:
- command behavior
- flags
- help text
- command routing

### Execution layer
- `tagslut/exec/`

Use for:
- transcoding
- DJ pipeline execution
- operational task flow

### DJ logic
- `tagslut/dj/`

Use for:
- DJ-specific logic
- XML/export-related behavior
- DJ metadata helpers

### Storage
- `tagslut/storage/`
- `tagslut/storage/v3/`

Use for:
- database behavior
- schema
- migrations
- identity model
- migration runner and verification

### Tests
- `tests/dj/`
- `tests/exec/`
- `tests/storage/`
- `tests/storage/v3/`

Use for:
- verifying the smallest relevant behavior
- locating expected current contracts

### Audit and documentation
- `docs/audit/`

Use only when:
- the task is about repo state
- docs/code mismatch
- workflow or architecture audit

## Implemented facts that matter

- `tagslut` is the canonical CLI command.
- The `dedupe` alias was removed.
- The repo already contains v3 database work.
- Migration `0006` is implemented.
- `0006` added:
  - `label`
  - `catalog_number`
  - `canonical_duration_s`
  - partial indexes for non-null identity lookups
  - composite normalized artist/title index
- Migration verification exists through the v3 migration runner.
- DJ flow is staged and explicit, not hypothetical.

## Routing by task

### If the task is a bug
Start with:
1. failing command or traceback
2. nearest relevant module
3. nearest relevant test

### If the task is a CLI mismatch
Start with:
1. `tagslut/cli/commands/`
2. help text
3. relevant tests

### If the task is a DB or migration issue
Start with:
1. `tagslut/storage/`
2. `tagslut/storage/v3/`
3. `tests/storage/`
4. `tests/storage/v3/`

### If the task is a DJ pipeline issue
Start with:
1. `tagslut/dj/`
2. `tagslut/exec/`
3. `tests/dj/`
4. `tests/exec/`

## Do not preload

Avoid reading unless the task explicitly requires it:
- session recaps
- logs
- backups
- historical plans
- broad synthesis docs
- generated outputs
- database files
- media libraries

## Working rule
Inspect the smallest relevant surface first.

## Objectives

Primary objective
Maintain a working CLI tool for managing the music library and DJ workflow.

Key goals
- Preserve current CLI behavior.
- Keep the database schema valid and migrations safe.
- Maintain the DJ pipeline (mp3 → dj → XML export).
- Fix bugs with minimal changes.

Avoid
- large refactors
- speculative redesigns
- changing database structure unless required.


## Task types

Bug fix
- reproduce the error
- inspect the relevant module
- apply the smallest patch
- verify with pytest

CLI change
- inspect the command module
- update argument parsing or behavior
- update tests if needed

Database task
- inspect storage/v3
- verify migration safety
- update schema or queries if required

DJ pipeline task
- inspect dj/ and exec/
- modify only the stage involved
- verify using DJ tests

