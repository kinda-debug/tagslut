# CODEX_AGENT.md

## Repository role
tagslut is a CLI-first Python project for building and managing DJ-ready music libraries.

Preserve existing behavior unless a task explicitly changes it.

## Canonical command
The only supported CLI entrypoint is:

poetry run tagslut

The `dedupe` alias was removed.

## Current architecture highlights

### Storage
The project uses the v3 identity model.

Migration `0006` is implemented and adds:
- label
- catalog_number
- canonical_duration_s
- partial indexes for identity lookups
- normalized artist/title composite index

Migration verification is handled by the v3 migration runner.

### DJ pipeline
Typical path:

FLAC → tagslut mp3 → tagslut dj → Rekordbox XML export

## Working rules
- start from failing command or test
- inspect minimal code surface
- prefer small reversible patches
- avoid repo-wide refactors
- avoid touching database files unless required

## Tests
Prefer targeted pytest runs over the full suite.
