# Script Surface (Canonical vs Legacy)

This file is the authoritative map of where to run things in this repo.

Policy and deprecation rules are defined in:
- `docs/SURFACE_POLICY.md`

## Canonical Entry Points

1. `poetry run tagslut intake ...`
Role: Download/intake orchestration and prefilter operations.

2. `poetry run tagslut index ...`
Role: Inventory registration, duplicate checks, duration checks, and metadata enrichment for indexed files.

3. `poetry run tagslut decide ...`
Role: Policy-profile listing and deterministic plan generation.

4. `poetry run tagslut execute ...`
Role: Execute move/quarantine/promote workflows from plans.

5. `poetry run tagslut verify ...`
Role: Validate duration/recovery/parity and move receipt consistency.

6. `poetry run tagslut report ...`
Role: M3U and operational reports (duration, recovery, plan summaries).

7. `poetry run tagslut auth ...`
Role: Provider authentication and token lifecycle flows.

8. `poetry run tagslut export usb ...`
Role: Export a source folder of MP3/FLAC tracks to a Pioneer CDJ-ready USB (writes PIONEER/ database via pyrekordbox, creates crate, outputs manifest).

## Rebrand Invocation

The preferred command brand is now `tagslut`.

Compatibility aliases:

### `dedupe` — ⚠️ RETIRING June 2026

The `dedupe` entry point is a deprecated alias for `tagslut`. It emits a deprecation warning
on every invocation and will be removed from `pyproject.toml` on **2026-06-01**.

**Migration:** Replace all uses of `dedupe [args]` with `tagslut [args]`.

Timeline:
- **Now → May 2026**: `dedupe` emits a deprecation warning to stderr on every invocation.
- **2026-05-01**: Alias frozen — no new subcommands added under `dedupe`.
- **2026-06-01**: `dedupe` entry point removed.

## Operational Wrappers (Active)

These wrappers are active convenience entrypoints around canonical intake/report flows:

1. `tools/get <url>`
Role: Unified URL router.
- `tidal.com` -> `tools/tiddl`
- `beatport.com` -> `tools/get-sync`

2. `tools/get-sync <beatport-url>`
Role: Beatport sync mode (download missing + build merged M3U).

3. `tools/get-report <beatport-url>`
Role: Beatport report-only mode (no download).

4. `tools/tagslut [args...]`
Role: Local wrapper for `python -m tagslut`.

5. `tools/tag-build [options]`
Role: Build M3U from DB for library FLAC files missing ISRC.

6. `tools/tag-run --m3u <path> [options]`
Role: Run `onetagger-cli` on a symlink batch from M3U and emit summary artifacts.

7. `tools/tag [options]`
Role: Combined build + run OneTagger workflow with defaults.

## Retired Command Groups

Retired in Phase 5 (not operator-facing):
- tagslut scan
- tagslut recommend
- tagslut apply
- tagslut promote
- tagslut quarantine ...
- tagslut mgmt ...
- tagslut metadata ...
- tagslut recover ...

Internal hidden commands (`_mgmt`, `_metadata`, `_recover`) may exist for
code-organization compatibility, but they are implementation details only and
not operator-facing entry points.

Use `tagslut intake/index/decide/execute/verify/report/auth` for new work.

## Recovery Command Status

- `tagslut recovery` is currently a minimal stub logger and does not implement the full move pipeline described in some historical docs.
- For move execution today, use:
  - Plan generation scripts in `tools/review/`
  - `tools/review/move_from_plan.py`
  - `tools/review/quarantine_from_plan.py`
  - `tools/review/promote_by_tags.py` (`--move-log` for JSONL move audit output)
- Compatibility contract for these executors:
  - `docs/MOVE_EXECUTOR_COMPAT.md`
  - `docs/archive/phase-specs-2026-02-09/` (phase runbooks and verification reports)

## Directory Ownership

- `tagslut/`: Productized CLI/package code.
- `tools/review/`: Active operational scripts.
- `legacy/tools/`: Archived historical scripts kept for reference and compatibility.
- `tools/review/promote_by_tags_versions/`: Historical snapshots.

## Rules for Keeping This Logical

1. New operational logic should go in `tagslut/` or `tools/review/`, not `legacy/`.
2. If a script is superseded, move it to an archive location and add a note in `legacy/tools/README.md`.
3. Keep docs aligned with real command help:
   - `poetry run tagslut --help`
   - `poetry run tagslut index --help`
   - `poetry run tagslut execute --help`
   - `poetry run tagslut auth --help`
4. Keep generated runtime outputs under `artifacts/` (`artifacts/logs`, `artifacts/tmp`, `artifacts/db`) instead of repo root.
