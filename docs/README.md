# docs/ — Documentation Index

This directory contains the active operator and developer documentation for the `tagslut` package.

## Active Docs

| File | Purpose |
|------|---------|
| `ARCHITECTURE.md` | System design, data flow, and provenance model |
| `OPERATIONS.md` | CLI reference, common operations, and the operations manual |
| `WORKFLOWS.md` | Step-by-step library ingestion and recovery workflows |
| `TROUBLESHOOTING.md` | Debugging guide and known failure modes |
| `DJ_REVIEW_APP.md` | DJ review web app usage and configuration |
| `DJ_WORKFLOW.md` | DJ-specific intake and playlist workflows |
| `PROJECT.md` | Project goals, scope, and decision log |
| `PROGRESS_REPORT.md` | Running progress and milestone notes |
| `PHASE5_LEGACY_DECOMMISSION.md` | Legacy module decommission plan |
| `SURFACE_POLICY.md` | Script/CLI surface policy and stability tiers |
| `SCRIPT_SURFACE.md` | Enumeration of all public CLI entry points |
| `REDESIGN_TRACKER.md` | Active redesign tasks and status |

## Legacy code location

All **retired scripts and historical tooling** live in **`legacy/`** at the
repository root.  There is no `tagslut/legacy/` sub-package.  Keeping legacy
code inside the installable Python package would expose it as `tagslut.legacy`
and blur the boundary between the active package surface and retired tooling.
The root-level `legacy/` directory is not installed as part of the package and
is not importable.

See `legacy/README.md` for the full inventory and policy.

## Audit Notes

### `tagslut_import/` (top-level directory)

**Audit date:** 2026-03

Following a structural audit (see `docs/TAGSLUT_IMPORT.md`), the `tagslut_import/` top-level directory was confirmed **absent** from this repository. It is not an importable package, is not listed in `pyproject.toml`, and has no files or references anywhere in the codebase. No action to restore or create it is required.

## Archive

Historical and retired documents live in `docs/archive/`. See `docs/archive/README.md` for the index.
