<!-- Status: Active document. Synced 2026-03-12 after DJ role/profile documentation refresh. Historical or superseded material belongs in docs/archive/. -->

# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

## [Unreleased] - 2026-04-13

## [Unreleased] - 2026-04-18

### Added
- Repo-local operator wrappers: `tools/ts-get`, `tools/ts-enrich`, and `tools/ts-auth`.
- `env_exports.sh.template` for machine-local downloader configuration (`BEATPORTDL_CMD`, `STREAMRIP_CMD`, `STREAMRIP_CONFIG`) with optional staging-root overrides.
- Shared shell-wrapper bootstrap via `tools/_wrapper_common.sh`, internal Beatport launcher boundary via `tools/_beatportdl.sh`, and repo-local wrappers for `tools/streamrip` and `tools/spotiflac-next`.
- Regression coverage for Qobuz/ReccoBeats provider-state handling and ReccoBeats router access.

### Changed
- `tools/get` now relies on wrapper-backed downloader resolution instead of machine-specific absolute paths, derives Beatport/Qobuz staging roots from `STAGING_ROOT`, and uses a stable manifest lookup when returning promoted playlists.
- Active wrapper scripts now share a common path/env bootstrap and call the repo-local Python/runtime surface consistently.
- SpotiFLAC-Next now launches through `tools/spotiflac-next`, resolves the current app-bundle executable automatically, detaches by default, and writes logs to `artifacts/logs/spotiflacnext/`.
- Provider status reporting now reflects real credential presence for Qobuz (`app_id`, `app_secret`, `user_auth_token`) and ReccoBeats (`api_key`) instead of reporting both as always authenticated.
- ReccoBeats remains routable for public ISRC / track-id metadata lookups even when status reports `enabled_unconfigured`.

### Fixed
- `tagslut get <local-path>` local flow no longer drops output generation behind an unreachable block and no longer self-locks the SQLite DB when output artifacts are built after writeback.

### Added
- Reconcile task checkpoints: commands read/write `data/checkpoints/reconcile_YYYYMMDD_HH.json` and prompt before re-running completed tasks.
- `tagslut v3 migrate` — preview/apply pending v3 schema migrations (dry-run by default).
- `tagslut mp3 verify-schema` — Task 1 table verification + JSONL log + checkpoint.
- `scripts/transcode_m4a_to_flac_lossless.sh` — transcode lossless `.m4a` (ALAC or FLAC-in-M4A) to `.flac` with optional AAC `.m4a` → 320k MP3.
- `scripts/verify_transcodes.sh` — verify `.m4a` → `.flac` (bit-perfect PCM MD5) and optional AAC `.m4a` → `.mp3` (duration + decode).

### Changed
- `tagslut mp3 reconcile` now reconciles from `--scan-csv`; legacy direct-root scan moved to `tagslut mp3 reconcile-library` (alias kept: `reconcile-scan`).
- Lexicon metadata import accepts `main.db` or backup ZIP snapshots containing `main.db`, matches normalized `Track.locationUnique` before `Track.location`, and preserves Lexicon source payloads in `track_identity.canonical_payload_json`.
- Lexicon metadata import considers trusted/compatibility DJ MP3 roots: `/Volumes/MUSIC/MP3_LIBRARY/`, `/Volumes/MUSIC/DJ_LIBRARY/`, and `/Volumes/MUSIC/DJ_POOL_MANUAL_MP3/`.

### Fixed
- Metadata enrichment writeback now merges provider canonical fields into the linked
  `track_identity` row via `asset_file` → `asset_link`, writes schema-aware
  `library_track_sources` snapshots for legacy and v3 DBs, and lets FLAC
  canonical writeback fall back to `files.canonical_*` when identity fields are blank.
- Lexicon field writes now log as `lexicon_field_import` with old/new values.
- Missing masters report no longer depends on `track_identity.status` and prefers `v_dj_ready_candidates` when available.

## [Unreleased] - 2026-03-29

### Added - Auth
- `tagslut auth logout <provider>` for authenticated providers. `tidal` performs a best-effort server-side logout before clearing local token state; `beatport` clears local token state only.

### Changed - Auth
- `tagslut auth login <provider>` now exits early when a valid non-expired token already exists and supports `--force` / `-f` to re-authenticate explicitly.

## [Unreleased] - 2026-03-26

### Fixed
- `get_intake_console.py` — artifact selection now derives run stamp from raw log
  filename and prefers files matching that exact stamp, preventing stale precheck
  CSVs from prior runs being attached to the current report.
- `tools/get-intake` — detects Tidal auth failure (`tidal_token_missing`) during
  link extraction and reports it clearly. With `--force-download`, bypasses precheck
  and falls back to direct Tidal download instead of silently reporting `total=0`.

### Changed
- Replaced `flake8-custom-import-rules` dev dependency (unused, pinned `typer <0.16`)
  with `tiddl ^3.2.2` (Python ≥3.13 marker). Unblocks `typer >=0.20` for tiddl CLI.

## [Unreleased] - 2026-03-23

### Added
- `tagslut mp3 scan` — scan one or more MP3 root directories, collect ID3 tags + audio
  metadata (bitrate, sample rate, duration, SHA-256), and write a stable manifest CSV.
  Progress printed every 500 files; each file logged to `data/logs/reconcile_scan_<run_id>.jsonl`.
- `tagslut mp3 reconcile-scan` — enhanced multi-tier reconcile that reads a manifest CSV
  and matches each MP3 against `track_identity` via: Tier 1 filename pattern, Tier 2 ISRC,
  Tier 3 ID3 title+artist, Tier 4 fuzzy (flag-only). Unmatched files become stubs.
  All decisions written to `reconcile_log` and a JSONL audit log. Idempotent, transactional.
- `tagslut mp3 missing-masters` — generate a GitHub-flavored Markdown report of orphaned
  MP3s (Section A, HIGH/MEDIUM/LOW priority) and FLACs with no MP3 derivative (Section B).
- `tagslut lexicon import` — import Lexicon DJ library track metadata into TAGSLUT_DB.
  Matches by path, title/artist, or streaming ID. Writes only NULL fields by default
  (`--prefer-lexicon` to overwrite). Hard rules: `dj_tags_json` is never touched;
  the `set_role='peak'` profile row is never modified; no new `dj_track_profile` rows created.
- `tagslut lexicon import-playlists` — import allow-listed Lexicon playlists into
  `dj_playlist` / `dj_playlist_track`. Enforces skip-list precisely; `fucked` playlist
  tracks → `dj_admission.status='needs_review'`; `Duplicate Tracks *` → `is_duplicate`
  flag in notes. Ordinal from Lexicon position is preserved. Idempotent.
- `tagslut master scan` — register FLACs from `MASTER_LIBRARY` into `asset_file` +
  `asset_link`. Matches existing identities via ISRC then title/artist; creates stubs
  for unmatched files. Progress every 1,000 files. Idempotent.
- `reconcile_log` table DDL and migration 0010 (if not already applied).
- New test files: `tests/exec/test_mp3_reconcile.py`, `tests/exec/test_master_scan.py`,
  `tests/dj/test_lexicon_import.py`, `tests/dj/test_lexicon_playlists.py`,
  `tests/storage/test_reconcile_migration.py` — 58 new tests, all passing.

### Changed
- `tagslut cli main.py` — registered `lexicon` and `master` command groups.

## [Unreleased] - 2026-03-24

### Changed - DJ Pipeline Discipline + XML Invariants
- Docs now match the literal 4-stage curated-library pipeline commands (no `--master-root` on `tagslut mp3 build`), and DJ-adjacent docs explicitly point back to `docs/DJ_PIPELINE.md` as the operator source of truth.
- `tagslut intake --mp3/--dj` is explicitly marked as a legacy convenience shortcut and emits a runtime warning pointing operators to the explicit 4-stage pipeline.
- `tools/get --dj` help + runtime output are strengthened to an explicit `[LEGACY]` deprecation message with canonical pointers (`docs/DJ_PIPELINE.md`, `tagslut dj --help`).
- `tagslut/dj/xml_emit.py` is hardened:
  - deterministic track ordering is stable across initial emits and re-emits (no first-emit reordering drift),
  - re-emit from identical DB state warns when output is identical to a prior export and fails loudly if bytes change without a DB-state change,
  - `dj xml patch` requires the prior on-disk XML to exist and match its stored manifest hash before proceeding.
- `tagslut/dj/admission.py` now assigns stable Rekordbox TrackIDs at Stage 3 admission time (`dj_track_id_map`), making TrackID stability independent of Stage 4.

### Added
- Migration `0011_harden_dj_xml_invariants.sql`: `dj_validation_state` table plus invariant triggers for immutable `dj_track_id_map` rows and required `dj_export_state` manifests.

## [Unreleased] - 2026-03-15

### Added
- `tagslut intake <URL>` (alias: `tagslut intake url <URL>`): canonical URL intake
  workflow that runs `tools/review/pre_download_check.py` for precheck, then
  `tools/get` for downloads/promote. Supports `--mp3 --mp3-root <dir>` for full-tag
  MP3 assets and `--dj --dj-root <dir>` for separate DJ copies (implies `--mp3`;
  MP3 asset library and DJ library are distinct roots). Every invocation writes a
  structured JSON artifact under `artifacts/intake/` with precheck summary,
  per-stage status, and final disposition.

## [Unreleased] - 2026-03-16

### Added
- `make check-v3-identity-integrity`: minimal routine v3 identity integrity proof surface (migration runner, schema equivalence, transaction boundaries, and provider-uniqueness migrations).

### Changed
- V3 identity hardening docs tightened to match literal migration audit behavior; helper-level identifier policy and runtime `merged_into_id` cycle handling are now explicit.

### Fixed
- `poetry run pytest ...` no longer fails on transitive `pylama` pytest plugin autoload (plugin disabled via pytest `addopts` in `pyproject.toml`).

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
- **`tools/get --dj`** remains a legacy wrapper path. It now emits an explicit runtime deprecation warning that points operators to the canonical 4-stage DJ pipeline in `docs/DJ_PIPELINE.md`, while the legacy forwarding path to `tools/get-intake` remains available for compatibility.
- **`docs/DJ_PIPELINE.md`**: added as the concise canonical workflow reference. **`docs/DJ_WORKFLOW.md`** remains the extended operator guide and legacy-wrapper rationale.
- **`docs/DB_V3_SCHEMA.md`**: new "DJ Pipeline Tables (migration 0010)" section documenting `mp3_asset`, `dj_admission`, `dj_track_id_map`, `dj_playlist`, `dj_playlist_track`, `dj_export_state`, `reconcile_log` with ownership rules and invariants.
- **`AGENT.md`**: `tagslut mp3` added to canonical surface; new "DJ Pipeline (Canonical 4-Stage Workflow)" section replaces the former `tools/get --dj` shortcut.
- **`README.md`**, **`docs/OPERATIONS.md`**, **`docs/WORKFLOWS.md`**, **`docs/SCRIPT_SURFACE.md`**, **`docs/ARCHITECTURE.md`**, and **`docs/DJ_POOL.md`**: `tools/get --dj` marked as legacy, stage numbering aligned around intake -> mp3 -> dj -> xml, and `docs/DJ_PIPELINE.md` made the primary DJ workflow reference.

### Invariants enforced
- One `dj_track_id_map` row per `dj_admission`; `rekordbox_track_id` is never reassigned.
- `patch_rekordbox_xml` verifies SHA-256 of prior output file against `dj_export_state.manifest_hash` before writing.
- `emit_rekordbox_xml` is byte-deterministic: same DB state → identical XML file on repeated emits.
- `dj validate` is required before `dj xml emit` unless `--skip-validation` is passed explicitly.

### Removed
- misleading documentation that treated wrapper-driven `tools/get --dj` behavior as the canonical curated-library workflow.

## [Unreleased] - 2026-03-23

### Changed - DJ Pipeline Contract

- README, `AGENT.md`, `docs/DJ_PIPELINE.md`, `docs/ROADMAP.md`, and the `tagslut dj` / `tagslut mp3` help surface now present the same primary curated-library sequence: `tagslut intake` -> `tagslut mp3 build|reconcile` -> `tagslut dj backfill` -> `tagslut dj validate` -> `tagslut dj xml emit|patch`.
- `tools/get --dj` and `tools/get-intake --dj` now print the same `[LEGACY] --dj is deprecated. Use the 4-stage pipeline. See: tagslut dj --help` warning in help text and at runtime.
- `tagslut/dj/xml_emit.py` now refuses any attempt to reuse a `dj_admission` with a different existing `TrackID`, and it checks determinism against the latest prior export for the same DJ `state_hash`, not just the latest export row overall.
- `tests/e2e/test_dj_pipeline.py` now proves the requested E2E-3/E2E-4/E2E-5 scenarios with DB assertions plus XML/manifest assertions.

## [Unreleased] - 2026-03-22

### Added - DJ Pipeline Hardening

- `docs/DJ_PIPELINE.md`: concise canonical 4-stage DJ pipeline reference covering intake masters, MP3 build/reconcile, DJ admission/validation, and Rekordbox XML emit/patch.
- `docs/audit/DJ_PIPELINE_DOC_TRIAGE.md`: active-doc DJ pipeline triage table for essential versus archived surfaces.
- E2E proofs for an executing Stage 2 MP3 build, stable playlist ordering with ordinal collisions, and a determinism-regression guard when XML output changes without a DJ DB state change.
- FFmpeg post-transcode MP3 validation in `tagslut/exec/transcoder.py`: successful ffmpeg exit is no longer accepted on its own. Stage 2/DJ-pool transcodes now fail fast if the output file is missing, suspiciously small, unreadable by mutagen, or shorter than 1 second.
- Focused transcode failure coverage in `tests/exec/test_mp3_build_ffmpeg_errors.py`, including missing ffmpeg, non-zero ffmpeg exit, corrupt output detection, and DJ pool wizard failure surfacing.
- `dj_validation_state` audit tracking plus `tests/exec/test_dj_xml_preflight_validation.py`: `dj validate` now records pass/fail state for the current DJ DB `state_hash`, and `dj xml emit` requires a matching passing validation before writing XML.

### Changed - DJ Pipeline Hardening

- README, AGENT, CLAUDE, `.claude/CLAUDE.md`, and active DJ docs now present the same canonical operator flow: `tagslut intake` -> `tagslut mp3 build|reconcile` -> `tagslut dj admit|backfill` -> `tagslut dj validate` -> `tagslut dj xml emit|patch`.
- `tools/get --dj` help and runtime stderr now use an explicit `[LEGACY]` warning and point operators to `docs/DJ_PIPELINE.md` or `tagslut dj --help`.
- `tools/get-intake --dj` help text now marks the wrapper-driven DJ path as legacy-only output.
- `tagslut mp3 --help` and `tagslut dj --help` now align their stage numbering with the canonical 4-stage pipeline.
- `tagslut/dj/xml_emit.py` now enforces deterministic playlist/member ordering and stores a DJ DB state hash in `dj_export_state.scope_json`, failing loudly if XML changes without a DB-state change.
- Stage 4 XML emit now requires a prior passing `dj validate` run for the current `state_hash`; `--skip-validation` remains only as a warning-emitting emergency bypass.

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
