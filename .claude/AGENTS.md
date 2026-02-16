# AGENTS.md - Agent Guidance for tagslut Repo

## Philosophy

This repository manages a **music library deduplication and rebuild effort** after major data loss. The project is about **sanity, deduplication, provenance, and deterministic operations**.

- The project is **tagslut** (implemented in the `tagslut/` package).
- **bpdl** and **tiddl** are download tools inside the project.
- **Yate** is the manual precision tagger for edge cases.
- Scanning, indexing, planning, execution, verification, and reporting are first-class workflow stages.

## Core Goals

1. Rebuild from trusted sources (Beatport/Tidal/Qobuz) with provenance.
2. Keep a reliable inventory DB for duplicate prevention and decisioning.
3. Enforce DJ safety gates (especially duration checks).
4. Keep the operational surface simple and canonical.
5. Preserve move-only semantics for file relocation workflows.

## Canonical Command Surface (Use These)

1. `tagslut intake ...`
2. `tagslut index ...`
3. `tagslut decide ...`
4. `tagslut execute ...`
5. `tagslut verify ...`
6. `tagslut report ...`
7. `tagslut auth ...`

Compatibility aliases:
- `dedupe ...`

Reference map:
- `docs/SCRIPT_SURFACE.md`
- `docs/SURFACE_POLICY.md`

## Dos and Don'ts

### DO

- Read `REPORT.md` before structural changes.
- Use canonical commands only.
- Register new downloads: `tagslut index register <path> --source <source>`.
- Pre-check duplicates before downloads: `tagslut index check <path> --source <source>`.
- Run DJ duration checks: `tagslut index duration-check <path> --dj-only`.
- Generate playlists via `tagslut report m3u <path>`.
- Verify moves/receipts after execution: `tagslut verify receipts --db <db>`.
- Keep file operations move-only and auditable.
- Keep docs updated when workflow behavior changes.

### DON'T

- Don't use retired wrappers (`mgmt`, `metadata`, `recover`, `scan`, `recommend`, `apply`, `promote`, `quarantine`).
- Don't copy music files as part of operational dedup flows.
- Don't overwrite/delete media without explicit operator intent.
- Don't change folder structure assumptions without checking real filesystem state.
- Don't leave orphaned docs in active surface when no longer part of workflow.

## Workflow Reference

### Intake + Index

```bash
# Download/intake orchestration
poetry run tagslut intake run --batch-root /Volumes/DJSSD/beatport <url>

# Register and check
poetry run tagslut index check <path> --source bpdl
poetry run tagslut index register <path> --source bpdl
```

### Decide + Execute + Verify

```bash
# Deterministic planning
poetry run tagslut decide plan --policy library_balanced --input <in.json> --output <plan.json>

# Move execution
poetry run tagslut execute move-plan <plan.csv>
poetry run tagslut execute quarantine-plan <plan.csv>
poetry run tagslut execute promote-tags --source-root <src> --dest-root <dst>

# Validation
poetry run tagslut verify receipts --db <db>
poetry run tagslut verify parity --db <db>
```

### Reporting + Auth + Enrichment

```bash
poetry run tagslut report m3u <path>
poetry run tagslut report duration --db <db>

poetry run tagslut auth status
poetry run tagslut auth login tidal
poetry run tagslut index enrich --db <db> --recovery --execute
```

## Tool Reference

| Tool | Role |
|---|---|
| `tagslut intake` | Intake orchestration and prefilter |
| `tagslut index` | Inventory, duplicate checks, duration checks, enrich |
| `tagslut decide` | Deterministic planning with policy profiles |
| `tagslut execute` | Move/quarantine/promote plan execution |
| `tagslut verify` | Receipts, parity, recovery and duration verification |
| `tagslut report` | M3U and operational reporting |
| `tagslut auth` | Provider auth status/login/init/refresh |
| `tools/get` | URL router to `tools/tiddl` or `tools/beatportdl/bpdl/bpdl` |
| `tools/review/*` | Active execution helpers and compatibility scripts |

## References

- `REPORT.md` - project strategy and rationale
- `docs/SCRIPT_SURFACE.md` - canonical command map
- `docs/SURFACE_POLICY.md` - surface policy and gates
- `docs/REDESIGN_TRACKER.md` - migration tracker
- `docs/PHASE5_LEGACY_DECOMMISSION.md` - decommission plan
- `tools/beatportdl/bpdl/README.md` - BeatportDL config reference
- `docs/archive/` - historical docs/assets no longer in active surface
