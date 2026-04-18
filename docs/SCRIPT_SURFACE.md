<!-- Status: Active document. Synced 2026-04-18 after command-surface cleanup. Historical or superseded material belongs in docs/archive/. -->

# Script Surface (Canonical vs Legacy)

This file is the authoritative map of where to run things in this repo.

Policy and deprecation rules are defined in this file. Superseded surface
policy material lives under `docs/archive/`.

## Visible Top-Level Entry Points

1. `poetry run tagslut get ...`
Role: Download and ingest a provider URL or local path.
- `tagslut get <dir> --tag` is the local staged-intake shortcut for
  already-downloaded directory roots. It runs staged register ->
  enrich/art/promote -> named M3U export with source auto-detection.

2. `poetry run tagslut tag ...`
Role: Curate, fetch, apply, and sync metadata tags for library files.

3. `poetry run tagslut fix ...`
Role: Resume a blocked cohort or repair a specific file or identity.

4. `poetry run tagslut auth ...`
Role: Provider authentication and token lifecycle flows.

5. `poetry run tagslut admin ...`
Role: Advanced workflow groups. Use `admin intake`, `admin index`,
`admin execute`, `admin verify`, `admin report`, `admin library`,
`admin dj`, and `admin lexicon` for lower-level operations.

## Advanced and Transitional Entry Points

1. `poetry run tagslut intake ...`
Role: Canonical intake orchestration. Includes URL-based intake
(`tagslut intake <URL>`; alias: `tagslut intake url <URL>`) and root processing
(`tagslut intake process-root`).
Use `tagslut intake <URL>` as the primary entry point for Beatport/Tidal URLs;
`tools/get` is kept as a compatibility wrapper.

2. `poetry run tagslut admin intake stage`
Role: One-shot staged-files intake for already-downloaded roots. Runs register,
duration-check, and enrich/art/promote in sequence, then writes named M3U
exports for promoted files.

3. `poetry run tagslut index ...`
Role: Inventory registration, duplicate checks, duration checks, and metadata enrichment for indexed files.

4. `poetry run tagslut decide ...`
Role: Policy-profile listing and deterministic plan generation.

5. `poetry run tagslut execute ...`
Role: Execute move/quarantine/promote workflows from plans.

6. `poetry run tagslut verify ...`
Role: Validate duration/parity and move receipt consistency.

7. `poetry run tagslut report ...`
Role: M3U and operational reports (duration, plan summaries).

8. `poetry run tagslut auth ...`
Role: Provider authentication and token lifecycle flows.

9. `poetry run tagslut mp3 ...`
Role: MP3 derivative asset management (Stage 2 of the 4-stage DJ pipeline; prerequisite: Stage 1 intake).
- `mp3 build` — transcode preferred source asset(s) to MP3 and register in `mp3_asset` (lossless canonical first, provisional high-quality lossy allowed when linked)
- `mp3 reconcile` — scan an existing MP3 root (via `--mp3-root` or `$DJ_LIBRARY`) and register files in `mp3_asset`; unmatched files are preserved as provisional lineage rows instead of being dropped

10. `poetry run tagslut dj ...`
Role: DJ library admission, validation, and Rekordbox XML export (Stages 3 and 4).
- `dj admit` — admit a single identity into the DJ library (`dj_admission` row)
- `dj backfill` — admit all `mp3_asset` rows not yet in `dj_admission`
- `dj validate` — validate DJ library state (missing files, empty metadata)
- `dj xml emit` — emit deterministic Rekordbox XML from `dj_admission` state
- `dj xml patch` — re-emit XML verifying prior manifest, preserving stable TrackIDs
- legacy subcommands (`curate`, `export`, `pool-wizard`, `role`) remain available

11. `poetry run tagslut gig ...`
Role: Build and manage DJ gig sets.

12. `poetry run tagslut export ...`
Role: Export tracks to USB or DJ pools.

13. `poetry run tagslut init ...`
Role: First-run interactive initialization wizard.

14. `poetry run tagslut ops ...`
Role: Internal operator utilities for guarded maintenance workflows.
- `ops run-move-plan` — execute a move plan with preflight/postflight checks and receipt archival
- `ops plan-dj-library-normalize` — build DJ library normalization plans
- `ops relink-dj-pool` — apply DJ pool relink manifests and optional playlist rewrites
- `ops writeback-canonical` — write canonical tags back to FLAC files from a root or M3U; reads linked `track_identity.canonical_*` first and falls back to `files.canonical_*` for blank identity fields

15. `poetry run tagslut provider status`
Role: Check authentication and availability status for all configured metadata providers.

16. `poetry run tagslut postman ingest`
Role: Import Postman collection data from a Newman JSON report into v3 provenance.

17. `poetry run tagslut library import-rekordbox`
Role: Import a Rekordbox XML export into the library database.

18. `poetry run tagslut admin lexicon ...` or `poetry run tagslut lexicon ...`
Role: Import Lexicon DJ snapshot metadata and playlists.
- `lexicon import` — import Lexicon track metadata from `main.db` or a backup ZIP containing `main.db`; matches normalized `locationUnique` before `location` and preserves Lexicon provenance in `track_identity.canonical_payload_json`
- `lexicon import-playlists` — import Lexicon playlists from `main.db` or a backup ZIP containing `main.db`

19. `poetry run tagslut master scan`
Role: Scan the `MASTER_LIBRARY` root and register files.

20. `poetry run tagslut v3 ...`
Role: Database migration utilities and provenance inspection for operator/maintenance use only.
- `v3 migrate` — run or preview v3 schema migrations
- `v3 provenance show` — show ingestion fields and recent provenance events

## Rebrand Invocation

The preferred command brand is now `tagslut`.

Retired alias:

- `dedupe` has been removed as a console entry point.
- Migration: replace any remaining `dedupe [args]` usage with `tagslut [args]`.

## Repo-Local Tool Surface Standard

`tools/<name>` now means one of two things only:

1. A stable user-facing wrapper.
2. An internal helper prefixed with `_`.

Anything else under `tools/` is implementation code, payload data, or archive
material and is not part of the operator-facing command surface.

Wrapper contract for active shell entrypoints:

- shebang: `#!/usr/bin/env bash`
- strict mode: `set -euo pipefail`
- path bootstrap: resolve the wrapper directory from `BASH_SOURCE[0]`
- env bootstrap: source `tools/_load_env.sh` directly or via `tools/_wrapper_common.sh`
- repo Python: prefer `tools/tagslut` or repo-local `.venv/bin/python`
- failure style: exit immediately with a direct stderr error when a required
  downstream executable or config path is missing

## Repo-Local Tool Classification

Stable user-facing wrappers:

- `tools/auth`
  Role: zero-config token refresh/sync wrapper for active providers.
- `tools/deemix`
  Role: Deezer download wrapper plus optional auto-register.
- `tools/enrich`
  Role: zero-config enrichment wrapper using `$TAGSLUT_DB`.
- `tools/get`
  Role: stable intake/download wrapper around the active intake pipeline.
- `tools/get-intake`
  Role: advanced/backend intake wrapper for existing batch roots and direct
  pipeline control.
- `tools/get-report`
  Role: Beatport report-only wrapper around `tools/get-intake`.
- `tools/metadata`
  Role: stable metadata workflow wrapper for OneTagger-related operations.
- `tools/spotiflac-next`
  Role: stable repo-local wrapper around the macOS SpotiFLAC-Next app binary,
  with runtime logs written under `artifacts/logs/spotiflacnext/` by default.
- `tools/streamrip`
  Role: stable repo-local wrapper around the active Streamrip CLI.
- `tools/tagslut`
  Role: repo-local wrapper for `python -m tagslut`.
- `tools/tiddl`
  Role: stable repo-local wrapper around the active TIDDL CLI.
- `tools/ts-stage`
  Role: repo-local staging-intake wrapper around `tagslut admin intake stage`
  with source auto-detection for standard staging roots.

Compatibility aliases kept intentionally:

- `tools/beatport`
  Role: shell-history alias to `tools/get`.
- `tools/get-help`
  Role: shell-history alias to `tools/get --help`.
- `tools/metadata-audit`
  Role: alias to `tools/metadata audit`.
- `tools/tag`
  Role: alias to `tools/metadata tag`.
- `tools/tag-audiofeatures`
  Role: alias to `tools/metadata audiofeatures`.
- `tools/tag-build`
  Role: alias to `tools/metadata build`.
- `tools/tag-metadata`
  Role: alias to `tools/metadata metadata`.
- `tools/tag-run`
  Role: alias to `tools/metadata run`.
- `tools/tidal`
  Role: shell-history alias to `tools/get`.
- `tools/ts-auth`
  Role: PATH alias to `tools/tagslut auth login`.
- `tools/ts-enrich`
  Role: PATH alias to `tools/tagslut enrich`.
- `tools/ts-get`
  Role: PATH alias to `tools/get`.

Internal helpers:

- `tools/_beatportdl.sh`
  Role: internal resolver/launcher for BeatportDL. Hidden behind `tools/get`
  and `BEATPORTDL_CMD`.
- `tools/_console_ui.sh`
  Role: internal Rich/console formatting helper.
- `tools/_load_env.sh`
  Role: internal `.env` loader.
- `tools/_wrapper_common.sh`
  Role: shared shell-wrapper bootstrap for path/env/python resolution.

Implementation scripts and directories, not first-class wrappers:

- top-level `tools/*.py`
- `tools/dj/`
- `tools/metadata_scripts/`
- `tools/review/`
- `tools/launch_group.sh`
- `tools/rules/`
- `tools/baselines/`

Embedded payloads, not commands:

- `tools/beatportdl/`
  Role: embedded BeatportDL payload directory. The active executable is
  `tools/beatportdl/bpdl/beatportdl`, but operators should go through
  `tools/get` or `BEATPORTDL_CMD`.
- `tools/onetagger/`
  Role: embedded OneTagger payload directory. Operators should go through
  `tools/metadata` or the `tools/tag*` aliases.

Archive / non-surface:

- `tools/archive/`
- generated caches such as `tools/__pycache__/`

## Active Wrapper Notes

1. `tools/get <url>`
Role: legacy-compatible download wrapper around the canonical intake
pipeline. For new work, prefer `poetry run tagslut intake <url>`
when you want the product CLI directly.
- default behavior: precheck + download + tagging/enrich/art + promote + merged M3U
- Beatport URLs may download from TIDAL when a strict verified cross-match exists and TIDAL ranks higher by quality; Beatport remains the metadata origin for that URL.
- default output is concise; `--verbose` enables internal paths, artifact files, and batch snapshots
- high-level workflow flags: `--dj`, `--hoard`, `--no-hoard`, `--no-precheck`, `--force-download`, `--providers`, `--verbose`
- `--dj` writes DJ pool M3U files (per-batch and global dj_pool.m3u at MP3_LIBRARY root).
- work roots are split by intent: `FIX_ROOT`, `QUARANTINE_ROOT`, `DISCARD_ROOT`
- `--simple` keeps downloader-only behavior
- downloader boundaries:
  - TIDAL goes through `tools/tiddl`
  - Qobuz goes through `tools/streamrip` unless `STREAMRIP_CMD` overrides it
  - Beatport goes through `tools/_beatportdl.sh` unless `BEATPORTDL_CMD` overrides it

2. `tools/get-intake ...`
Role: advanced/backend intake engine.
- use for existing batch roots (`--no-download --batch-root ...`)
- use for `--m3u-only` or direct pipeline control
- default output is concise; use `--verbose` for wrapper/debug details
- not the recommended first command for normal downloads

3. `tools/get-report <beatport-url>`
Role: Beatport report-only mode (no download).

4. `tools/tagslut [args...]`
Role: repo-local wrapper for the canonical `tagslut` product CLI.

5. `tools/auth [tidal|beatport|qobuz|all]`
Role: token refresh/sync wrapper.
- TIDAL: delegates to `tools/tiddl auth refresh`
- Beatport: syncs from BeatportDL credentials, preferring the embedded payload
  under `tools/beatportdl/` unless overridden
- Qobuz: refreshes app credentials and syncs them to the active Streamrip config

6. `tools/enrich`
Role: zero-config enrichment wrapper. Reads `$TAGSLUT_DB` from environment.

7. `tools/metadata <subcommand>`
Role: stable repo-local metadata wrapper.
- `build` / `run`: direct OneTagger workflow phases
- `tag`: combined build + run workflow
- `metadata`, `audiofeatures`, `audit`, `normalize-genres`, `tag-genres`,
  `audit-tags`, `export-lexicon`, `compare-lexicon`, `sync-tags`: direct
  pass-through subcommands to implementation scripts

8. `tools/spotiflac-next [args...]`
Role: stable repo-local launcher for the macOS SpotiFLAC-Next app binary.
- default app bundle: `/Applications/SpotiFLAC-Next.app`
- resolves the executable from the app bundle `Info.plist`
- override app bundle with `SPOTIFLAC_NEXT_APP`
- override executable directly with `SPOTIFLAC_NEXT_BIN`
- runtime logs go to `artifacts/logs/spotiflacnext/` by default
- override log root with `SPOTIFLAC_NEXT_LOG_ROOT`
- default mode detaches immediately; use `--foreground` to stream logs in the terminal

9. `tools/ts-stage [root] [options...]`
Role: repo-local wrapper for one-shot staged-files intake.
- with no root, auto-processes non-empty immediate subdirectories of
  `$STAGING_ROOT` when the source can be inferred:
  - `bpdl` -> `bpdl`
  - `tidal` -> `tidal`
  - `StreamripDownloads` -> `qobuz`
  - `SpotiFLACnext` -> `spotiflacnext`
  - `SpotiFLAC` -> `legacy`
- with any other audio root, falls back to `legacy`
- with a root argument, infers the source from the root name/content
- forwards extra flags to `tools/tagslut admin intake stage ...`
- for `spotiflacnext`, `intake stage` auto-loads the newest log from
  `artifacts/logs/spotiflacnext/` (or `SPOTIFLAC_NEXT_LOG_ROOT`), runs
  `tagslut intake spotiflac`, then runs `index register`, `index duration-check`,
  `index register-mp3`, and `intake process-root`
- stage playlist export prunes orphan `.m3u` files in playlist output roots
  after writing current DB-referenced playlists

10. `tools/review/sync_phase1_prs.sh`
Role: maintainer-only helper for pushing the active Phase 1 branch stack with preserved PR scope boundaries.

## Embedded Source-Tree Integrations

- `SpotiFLAC-Module-Version/`
  Role: embedded source-tree integration on the active TIDAL fallback path in
  `tools/get-intake`.
  Policy: not a user-facing command surface. `tools/get-intake` may import it
  by prepending `SPOTIFLAC_MODULE_ROOT` (default:
  `$TAGSLUT_ROOT/SpotiFLAC-Module-Version`) to `sys.path` when the fallback is
  needed.

## Beets Status

Beets is configured as a sidecar via `config/beets/beets/config.yaml`, not as a
repo-local operator wrapper surface.

- `.venv/bin/beet` remains the raw venv entrypoint for manual sidecar use.
- No `tools/beet` wrapper is provided.
- That is intentional unless Beets becomes part of the active operator workflow.

## Transcode Helpers (Scripts)

- `scripts/transcode_m4a_to_flac_lossless.sh`
Purpose: Narrow M4A helper for lossless-first staging. Transcodes ALAC or FLAC-in-M4A to `.flac`, and can optionally route AAC `.m4a` to 320k MP3 while preserving metadata/artwork.
Flags: `--scan-path`, `--output-dir`, `--lossy-to-mp3`, `--overwrite`
Example: `scripts/transcode_m4a_to_flac_lossless.sh --scan-path /Volumes/MUSIC/staging/SpotiFLACnext --lossy-to-mp3`

- `scripts/verify_transcodes.sh`
Purpose: Sanity-check outputs from `transcode_m4a_to_flac_lossless.sh` (lossless pairs: bit-perfect PCM MD5; lossy pairs: duration+decode). Use this after either the helper script or the broader MP3 lineage flow.
Flags: `--scan-path`, `--lossy-mp3`
Example: `scripts/verify_transcodes.sh --scan-path /Volumes/MUSIC/staging/SpotiFLACnext --lossy-mp3`

- `scripts/resolve_lossless_winner.sh`
Purpose: Codec-aware per-stem winner selection for staging directories. Keeps lossless sources canonical and flags lossy stems when no lossless sibling exists.
Flags: `--scan-path`, `--dry-run`, `--overwrite`
Example: `scripts/resolve_lossless_winner.sh --scan-path /Volumes/MUSIC/staging/SpotiFLACnext --dry-run`

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

Internal hidden commands (`_mgmt`, `_metadata`) may exist for
code-organization compatibility only. They are implementation details, not
operator-facing commands.

Hidden top-level commands by policy:
- `tagslut canonize ...`
- `tagslut enrich-file ...`
- `tagslut explain-keeper ...`
- `tagslut show-zone ...`

Use visible top-level commands (`get`, `tag`, `fix`, `auth`, `admin`) for new
operator work. Use `tagslut admin ...` for lower-level workflow groups.

## Recovery Command Status

- `tagslut.recovery` is decommissioned and intentionally non-importable.
- Hidden compatibility shims for old recovery invocations were removed from active CLI surface.
- Recovery remains retired and archived at `legacy/tagslut_recovery/`.
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
