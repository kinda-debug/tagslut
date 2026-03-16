# AGENTS.md

## Repository identity

tagslut is a CLI-first Python project used to manage a canonical music library and produce DJ-ready exports.

The canonical command is:

poetry run tagslut

The `dedupe` alias has been removed.

---

## Current database reality

The repository already contains meaningful v3 storage work.

Migration `0006` exists and adds:

- label
- catalog_number
- canonical_duration_s
- identity lookup indexes
- normalized artist/title composite index

Migration verification is implemented through the v3 migration runner.

Do not describe the database layer as hypothetical.

---

## Working rules

When implementing changes:

1. start from a failing command, traceback, or test
2. inspect the smallest relevant module
3. apply the smallest possible patch
4. verify with a targeted pytest run

Avoid:

- large refactors
- speculative redesigns
- schema changes unless required
- modifying unrelated files

---

## Code surface

CLI  
tagslut/cli/

Execution layer  
tagslut/exec/

DJ logic  
tagslut/dj/

Storage and migrations  
tagslut/storage/  
tagslut/storage/v3/

Tests  
tests/dj/  
tests/storage/  

---

## Testing

Prefer targeted tests over full suite runs.

Example:

pytest tests/dj -q
pytest tests/storage -q

---

## Goal

Maintain a deterministic pipeline:

FLAC → mp3 → dj → Rekordbox XML export
