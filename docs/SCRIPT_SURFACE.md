<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

# Script Surface (Canonical vs Legacy)

This file is the authoritative map of where to run things in this repo.

Policy and deprecation rules are defined in:
- `docs/SURFACE_POLICY.md`

## Canonical Entry Points

1. `poetry run tagslut intake ...`
Role: Canonical intake orchestration. Includes URL-based intake
(`tagslut intake <URL>`; alias: `tagslut intake url <URL>`) and root processing
(`tagslut intake process-root`).
Use `tagslut intake <URL>` as the primary entry point for Beatport/Tidal URLs;
`tools/get` is kept as a compatibility wrapper.

2. `poetry run tagslut index ...`
Role: Inventory registration, duplicate checks, duration checks, and metadata enrichment for indexed files.

3. `poetry run tagslut decide ...`
Role: Policy-profile listing and deterministic plan generation.

4. `poetry run tagslut execute ...`
Role: Execute move/quarantine/promote workflows from plans.

5. `poetry run tagslut verify ...`
Role: Validate duration/parity and move receipt consistency.

6. `poetry run tagslut report ...`
Role: M3U and operational reports (duration, plan summaries).

7. `poetry run tagslut auth ...`
Role: Provider authentication and token lifecycle flows.

8. `poetry run tagslut mp3 ...`
Role: MP3 derivative asset management (Stage 2 of the 4-stage DJ pipeline).
- `mp3 build` — transcode preferred FLAC master(s) to MP3 and register in `mp3_asset`
- `mp3 reconcile` — scan an existing MP3 root and register files in `mp3_asset` without re-transcoding

9. `poetry run tagslut dj ...`
Role: DJ library curation, admission, validation, and Rekordbox XML export.
- `dj admit` — admit a single identity into the DJ library (`dj_admission` row)
- `dj backfill` — admit all `mp3_asset` rows not yet in `dj_admission`
- `dj validate` — validate DJ library state (missing files, empty metadata)
- `dj xml emit` — emit deterministic Rekordbox XML from `dj_admission` state
- `dj xml patch` — re-emit XML verifying prior manifest, preserving stable TrackIDs
- legacy subcommands (`curate`, `export`, `pool-wizard`, `role`) remain available

10. `poetry run tagslut gig ...`
Role: Build and manage DJ gig sets.

11. `poetry run tagslut export ...`
Role: Export tracks to USB or DJ pools.

12. `poetry run tagslut init ...`
Role: First-run interactive initialization wizard.

## Rebrand Invocation

The preferred command brand is now `tagslut`.

Retired alias:

- `dedupe` has been removed as a console entry point.
- Migration: replace any remaining `dedupe [args]` usage with `tagslut [args]`.

## Operational Wrappers (Active)

These wrappers are active convenience entrypoints around canonical intake/report flows:

1. `tools/get <url>`
Role: Legacy-compatible download wrapper around the canonical intake
pipeline. For new work, prefer `poetry run tagslut intake <url>`
so you get structured artifacts and explicit precheck/download/MP3
stages.
- default behavior: precheck + download + tagging/enrich/art + promote + merged M3U
- Beatport URLs may download from TIDAL when a strict verified cross-match exists and TIDAL ranks higher by quality; Beatport remains the metadata origin for that URL.
- default output is concise; `--verbose` enables internal paths, artifact files, and batch snapshots
- high-level workflow flags: `--dj`, `--hoard`, `--no-hoard`, `--no-precheck`, `--force-download`, `--providers`, `--verbose`
- `--dj` is deprecated legacy behavior. See `docs/DJ_WORKFLOW.md` for the canonical 4-stage DJ pipeline.
- work roots are split by intent: `FIX_ROOT`, `QUARANTINE_ROOT`, `DISCARD_ROOT`
- `--simple` keeps downloader-only behavior

2. `tools/get-intake ...`
Role: Advanced/backend intake engine.
- use for existing batch roots (`--no-download --batch-root ...`)
- use for `--m3u-only` or direct pipeline control
- default output is concise; use `--verbose` for wrapper/debug details
- not the recommended first command for normal downloads

3. `tools/get-report <beatport-url>`
Role: Beatport report-only mode (no download).

4. `tools/get-sync <beatport-url>`
Role: Deprecated compatibility alias for `tools/get <beatport-url>`.

5. `tools/tagslut [args...]`
Role: Local wrapper for `python -m tagslut`.

6. `tools/tag-build [options]`
Role: Build M3U from DB for library FLAC files missing ISRC.

7. `tools/tag-run --m3u <path> [options]`
Role: Run `onetagger-cli` on a symlink batch from M3U and emit summary artifacts.

8. `tools/tag [options]`
Role: Combined build + run OneTagger workflow with defaults.

9. `tools/review/sync_phase1_prs.sh`
Role: Maintainer-only helper for pushing the active Phase 1 branch stack with preserved PR scope boundaries.

## Canonical DJ Pool Builder

Primary operator-facing DJ pool workflow:
- `poetry run tagslut dj pool-wizard`

Canonical lower-level script path:
- `scripts/dj/build_pool_v3.py`

Archived legacy builder:
- `scripts/archive/build_export_v3.py`

New operator docs should point to `tagslut dj pool-wizard`. Script-level references should point to `scripts/dj/build_pool_v3.py`, not the archived export builder.

## Retired Command Groups

Retired in Phase 5 (not operator-facing):
- tagslut scan ...
- tagslut recommend
- tagslut apply
- tagslut promote
- tagslut quarantine ...
- tagslut mgmt ...
- tagslut metadata ...
- tagslut recover ...

Internal hidden commands (`_mgmt`, `_metadata`, `_recover`) may exist for
code-organization compatibility only. They are implementation details, not
operator-facing commands.

Hidden top-level commands by policy:
- `tagslut canonize ...`
- `tagslut enrich-file ...`
- `tagslut explain-keeper ...`
- `tagslut show-zone ...`

Use `tagslut intake/index/decide/execute/verify/report/auth/dj/gig/export/init` for new work.

## Recovery Command Status

- `tagslut.recovery` is decommissioned and intentionally non-importable.
- Hidden compatibility shims still exist for old invocations:
  - `tagslut recovery ...`
  - `tagslut verify recovery ...`
  - `tagslut report recovery ...`
  - `tagslut _recover ...`
- Those shims are not active recovery functionality. They exist only to fail clearly and point to `legacy/tagslut_recovery/`.
- Canonical operator path for end-to-end root processing:
  - `tagslut intake process-root --root <folder> [--db <db>]`
- Current v3-safe `process-root` usage is `identify,enrich,art,promote,dj`; legacy scan phases are blocked when `--db` points at a v3 database.
- For move execution today, use:
  - `tagslut execute move-plan --plan <plan.csv> [--db <db>] [--dry-run]`
  - Plan generation scripts in `tools/review/`
- Compatibility-only executors:
  - `tools/review/move_from_plan.py` (deprecated in favor of `tagslut execute move-plan`)
  - `tools/review/quarantine_from_plan.py`
  - `tools/review/plan_move_skipped.py`
  - `tools/review/quarantine_gc.py`
  - `tools/review/promote_by_tags.py` (`--move-log` for JSONL move audit output)
- Archived compatibility contract:
  - `docs/archive/legacy-root-docs-2026-03-06-md-cleanup/MOVE_EXECUTOR_COMPAT.md`
- Historical phase runbooks and verification reports:
  - `docs/archive/phase-specs-2026-02-09/`

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
