<!-- Status: Active document. Synced 2026-03-12 after DJ role/profile documentation refresh. Historical or superseded material belongs in docs/archive/. -->

# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

## [Unreleased] - 2026-03-14

### Added — Explicit 4-Stage DJ Pipeline
- **`tagslut mp3` command group** (`mp3 build`, `mp3 reconcile`): Stage 2 of the canonical DJ pipeline. `mp3 build` transcodes preferred FLAC masters to MP3 and registers results in `mp3_asset`. `mp3 reconcile` scans an existing MP3 root and registers files in `mp3_asset` by matching ISRC then title+artist, without re-transcoding.
- **`tagslut dj admit/backfill/validate`**: Stage 3 commands. `admit` creates a single `dj_admission` row; `backfill` auto-admits all unadmitted `mp3_asset` rows with `status=verified`; `validate` checks for missing MP3 files and empty metadata.
- **`tagslut dj xml emit/patch`**: Stage 4 commands. `emit` produces deterministic Rekordbox-compatible XML from `dj_admission` state, assigns stable `rekordbox_track_id` values in `dj_track_id_map`, and records a SHA-256 manifest in `dj_export_state`. `patch` verifies the prior manifest hash before re-emitting (fails loudly on tampering), preserving existing TrackIDs so Rekordbox cue points survive re-imports.
- **Schema migration `0010_add_dj_pipeline_tables.sql`**: seven DJ pipeline tables — `mp3_asset`, `dj_admission`, `dj_track_id_map`, `dj_playlist`, `dj_playlist_track`, `dj_export_state`, `reconcile_log` — integrated into `init_db()` via `_ensure_mp3_dj_tables()`.
- **`tagslut/dj/admission.py`**: `admit_track`, `backfill_admissions`, `validate_dj_library` with `DjValidationReport`.
- **`tagslut/dj/xml_emit.py`**: `emit_rekordbox_xml`, `patch_rekordbox_xml` with manifest integrity checking.
- **`tagslut/exec/mp3_build.py`**: `build_mp3_from_identity`, `reconcile_mp3_library`.
- **P0 contract tests** (`tests/exec/test_precheck_dj_contract.py`): shell-level tests for empty-PROMOTED_FLACS warning (P0-A), precheck-hit CONTRACT NOTE (P0-B), and provenance DB state (P0-C).
- **Unit tests** (`tests/dj/test_admission.py`, `tests/storage/test_mp3_dj_migration.py`).
- **Pipeline E2E tests** (`tests/dj/test_dj_pipeline_e2e.py`, `tests/e2e/test_dj_pipeline.py`): 28 tests covering all 5 E2E scenarios including byte-identical XML determinism, manifest hash integrity, stable TrackIDs across patch cycles, and loud failure on tampered XML.

### Changed
- **`tools/get --dj`** demoted to **legacy**: emits a runtime deprecation warning on stderr when `--dj` is passed, pointing operators to the 4-stage pipeline. The flag still forwards to `tools/get-intake` for backwards compatibility.
- **`docs/DJ_WORKFLOW.md`**: "Explicit 4-Stage Pipeline" section added at the top as the canonical workflow. `tools/get --dj` section clearly marked as legacy.
- **`docs/DB_V3_SCHEMA.md`**: new "DJ Pipeline Tables (migration 0010)" section documenting `mp3_asset`, `dj_admission`, `dj_track_id_map`, `dj_playlist`, `dj_playlist_track`, `dj_export_state`, `reconcile_log` with ownership rules and invariants.
- **`AGENT.md`**: `tagslut mp3` added to canonical surface; new "DJ Pipeline (Canonical 4-Stage Workflow)" section replaces the former `tools/get --dj` shortcut.
- **`README.md`**, **`docs/OPERATIONS.md`**, **`docs/WORKFLOWS.md`**, **`docs/SCRIPT_SURFACE.md`**: `tools/get --dj` marked as legacy, 4-stage pipeline added as the primary DJ workflow reference.

### Invariants enforced
- One `dj_track_id_map` row per `dj_admission`; `rekordbox_track_id` is never reassigned.
- `patch_rekordbox_xml` verifies SHA-256 of prior output file against `dj_export_state.manifest_hash` before writing.
- `emit_rekordbox_xml` is byte-deterministic: same DB state → identical XML file on repeated emits.
- `dj validate` is required before `dj xml emit` unless `--skip-validation` is passed explicitly.

## [Unreleased] - 2026-03-12
### Added
- `tools/review/sync_phase1_prs.sh` for pushing the active Phase 1 branch stack while preserving PR scope boundaries
- companion sidecar handling during `tagslut execute move-plan` and compatibility `move_from_plan.py` execution
- staged-root DJ FLAC tag enrichment via `tagslut intake process-root --phases dj`
- `files.dj_set_role` and `files.dj_subrole` columns with indices
  (migration `0008_add_dj_set_role.sql`); `DJ_SET_ROLES` and `DJ_SUBROLES`
  constants in `tagslut/storage/models.py` with `ValueError` validation
- `PoolProfile` dataclass and `pool_profile_from_dict` in
  `tagslut/dj/export.py`; `layout: "by_role"` support with role-subdirectory
  routing, `_unassigned/` fallback, `only_roles` filtering, and per-role M3U
  generation (`10_GROOVE.m3u` etc.)
- `tagslut/cli/dj_role.py`: `tagslut dj role set / bulk / export` CLI commands
  for batch `dj_set_role` / `dj_subrole` assignment
- `dj_set_role: str | None` field added to `TrackRow` in
  `tagslut/dj/transcode.py`

### Changed
- `tagslut intake process-root --dry-run` now previews the DJ phase without writing FLAC tags, MP3s, or `dj_pool_path`
- active root and `docs/` Markdown files were refreshed to match the current v3 operator surface

## [3.0.1] — 2026-03-06
### Added
- tagslut/_web/ package: Flask DJ review app wired as tagslut report dj-review
- classification_v2 promotion script (tagslut index promote-classification)

### Fixed
- Silent except Exception blocks across 13 modules now log
- Provider IDs written in recovery mode
- Type annotations added to db_reader.py and enricher.py

## [3.0.0] — 2026-03-06
### Added
- Canonical v3 CLI surface: intake, index, decide, execute, verify, report, auth
- Centralized move executor (tagslut.exec.engine) with MoveReceipt verification
- Policy engine (tagslut.policy) with deterministic planning and plan hashing
- V3 data model: asset_file, track_identity, asset_link, provenance_event, move_plan, move_execution tables
- DJ pipeline: gig builder, USB export, transcode, Rekordbox XML export
- Pre-download identity resolution (ISRC -> provider IDs -> fuzzy fallback)
- OneTagger ISRC enrichment wrappers (tools/tag, tag-build, tag-run)
- Classification v2: genre fallback + soft scoring (scripts/classify_tracks_sqlite.py)

### Changed
- Version bumped from 2.0.0 to 3.0.0
- Project description updated to management-first framing

### Removed
- Legacy CLI wrappers: scan, recommend, apply, promote, quarantine, mgmt, metadata, recover (all retired per Phase 5)
- Recovery-era framing and documentation

## [2.0.0] — 2025-02-01
### Changed
- Rebrand from dedupe to tagslut
- Recovery phase declared complete; library rebuilt
