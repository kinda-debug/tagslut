<!-- Status: Active document. Last major sync 2026-03-14. Note: sections describing
     the 4-stage DJ pipeline (backfill/validate/XML) and DJ_LIBRARY as a distinct
     folder reflect the pre-April 2026 architecture. Current model uses M3U-based
     DJ pool. See docs/DJ_POOL.md and docs/OPERATOR_QUICK_START.md for current state. -->

# Architecture

## Active System Shape

`tagslut` is a v3 library-operations system with four main layers:

1. intake and registration
2. identity and metadata management
3. move planning, execution, and provenance
4. downstream DJ export

The active code lives in `tagslut/`, `tools/`, and `scripts/`. Historical code and superseded plans live in `legacy/` and `docs/archive/`. See `docs/README.md` for the full active-doc index.

## Source selection (summary)
- Spotify URLs route through a tagslut-owned Spotify intake adapter that expands Spotify metadata first, then downloads per track with service fallback `qobuz -> tidal -> amazon`.
- TIDAL via tiddl is the primary source when available.
- Beatport-only tracks download via beatportdl (explicit, not fallback).
- Qobuz downloads via streamrip when a Qobuz URL is provided.
- Metadata providers: beatport → tidal → qobuz → reccobeats (audio features).

## Intake Layer

### Normal operator path

Use `tools/get <provider-url>` for day-to-day provider intake. It wraps:

- pre-download filtering
- provider download
- local tag prep
- promote/fix/quarantine/discard planning
- downstream playlist generation
- optional legacy DJ MP3 creation with `--dj` (deprecated; see
  `docs/WORKFLOWS.md` and `docs/OPERATOR_QUICK_START.md` for the current
  operator-facing DJ path)

Supported URL families in the active wrapper path:

- Spotify track/album/playlist URLs
- TIDAL URLs
- Beatport URLs
- Qobuz URLs
- Deezer URLs

### Staged-root path

Use `tagslut intake process-root` when files already exist under a root you want to process.

Current v3 rule:

- on a v3 DB, `process-root` should be used only for `identify,enrich,art,promote,dj`
- `register`, `integrity`, and `hash` are legacy-scan phases and are blocked by the v3 guard

The staged-root DJ phase is implemented in `tools/review/process_root.py` and can:

- enrich FLAC BPM/key/energy from v3 identity data
- fall back to Essentia when canonical BPM/key are missing
- transcode staged FLACs to the configured DJ pool
- preview this DJ-only work with `--phases dj --dry-run`

## Core Data Model

The authoritative v3 ownership model is:

- `asset_file`: physical file truth
- `track_identity`: canonical track truth
- `asset_link`: active asset-to-identity binding
- `preferred_asset`: one deterministic preferred asset per identity
- `identity_status`: lifecycle state for an identity
- `move_plan`: move intent and policy context
- `move_execution`: executed move attempt and outcome
- `provenance_event`: immutable audit event stream

See `docs/archive/CORE_MODEL.md`, `docs/archive/DB_V3_SCHEMA.md`, and
`tagslut/storage/v3/schema.py` for the table-level contract.

### Lexicon metadata evidence

Lexicon is an external metadata/workflow system. tagslut imports Lexicon state
from `main.db` snapshots, preferably backup ZIPs under
`/Users/georgeskhawam/Documents/Lexicon/Backups/`.

- Lexicon `Track` rows are the source for Lexicon-owned state.
- `Track.locationUnique` is the preferred path bridge, followed by
  `Track.location` and identity fallbacks.
- `Track.data`, `fingerprint`, `importSource`, and path evidence are preserved
  in `track_identity.canonical_payload_json`.
- File tags and Lexicon reports are downstream mirrors/evidence, not the
  authoritative Lexicon dataset.

## Execution and Provenance

Move planning and move execution are deliberately separate.

Typical flow:

1. generate a CSV or plan artifact
2. execute with `tagslut execute move-plan`
3. verify receipts/parity

`tagslut execute move-plan` is now the canonical plan executor. It writes:

- `move_plan` for intent
- `move_execution` for each attempted move
- `provenance_event` for the durable audit trail

Common per-track sidecars move with the audio file when execution succeeds or is previewed:

- `.lrc`
- `.cover.jpg`, `.cover.jpeg`, `.cover.png`
- `.jpg`, `.jpeg`, `.png`

The compatibility script `tools/review/move_from_plan.py` remains available but is deprecated in favor of the CLI command.

## DJ Layer

The repo still contains an explicit DB-backed 4-stage DJ pipeline, but the
current operator-facing Rekordbox path is the clean-pool plus optional
historical-seed reconstruction flow documented in `docs/WORKFLOWS.md` and
`docs/OPERATOR_QUICK_START.md`. Legacy wrapper-driven DJ output still exists
for compatibility, but it is deprecated and should not be treated as the
primary operator contract.

Separately, the repo now has a filesystem-only precursor utility,
`tools/build_dj_seed_from_tree_rbx`, for reconstructing a practical starting DJ
seed from the historical Rekordbox export tree in `tree_rbx.js`. That tool is
not part of the DB-backed validation pipeline: it reads `tree_rbx.js`, scans
`/Volumes/MUSIC/MP3_LIBRARY_CLEAN`, applies conservative strict-tier matching,
and writes a playlist plus review reports under an operator-specified output
directory.

### Explicit 4-stage pipeline (canonical)

The canonical DJ path is a linear, DB-backed pipeline with explicit state at each stage:

1. **Intake masters** — `tagslut intake <provider-url>` refreshes canonical master identity and provenance state. Spotify-origin acquisitions are recorded with `ingestion_method='spotify_intake'`; direct provider API downloads remain `provider_api`.
2. **Build or reconcile MP3s** — `tagslut mp3 build` / `tagslut mp3 reconcile` writes `mp3_asset` rows; lossless sources stay canonical and high-quality lossy sources remain provisional until a lossless source is reacquired
3. **Admit and validate** — `tagslut dj backfill` / `dj admit` promotes assets to `dj_admission`, then `tagslut dj validate` checks readiness
4. **Emit or patch XML** — `tagslut dj xml emit` / `dj xml patch` writes deterministic Rekordbox XML, preserves stable TrackIDs via `dj_track_id_map`, and records manifest hashes in `dj_export_state`

### Deprecated legacy wrapper path

`tools/get --dj` and `tools/get-intake --dj` still exist as compatibility wrappers.
They are not the supported curated-library workflow because they depend on legacy wrapper
branching and side effects.

The pipeline tables (`mp3_asset`, `dj_admission`, `dj_track_id_map`, `dj_playlist`,
`dj_playlist_track`, `dj_export_state`, `reconcile_log`) were applied to `music_v3.db`
via migration 0010 on 2026-03-14. See `docs/archive/DB_V3_SCHEMA.md` and
`tagslut/storage/v3/schema.py` for the full schema.

### Deterministic v3 DJ pool (pool-wizard)

For building a final cohort-based MP3 pool from `MASTER_LIBRARY`:

1. export DJ candidates
2. write DJ profile overlays
3. export DJ-ready rows
4. `tagslut dj pool-wizard` (preferred) or `scripts/dj/build_pool_v3.py` (lower-level)

This path is plan-first and produces deterministic manifests.

### Historical seed reconstruction

Use `tools/build_dj_seed_from_tree_rbx` when the goal is to recover prior
approved DJ relevance from a Rekordbox tree export without mutating DB or
filesystem truth.

- Input truth for relevance recovery: `tree_rbx.js`
- Candidate universe: `/Volumes/MUSIC/MP3_LIBRARY_CLEAN`
- Output contract: M3U seed playlist, missing CSV, ambiguous CSV, JSONL manifest
- Safety model: read-only outside `--output-dir`
- Matching scope: exact ISRC, exact normalized artist/title, then exact
  artist/title narrowed by deterministic local context

This utility is intentionally separate from the broader provider-download and
metadata-provider architecture. It is a precursor input to later curation, not a
replacement for intake, enrichment, or DB-backed DJ admission.

## Zones, Lifecycle, and Work Roots

Two different concepts coexist and should not be conflated:

- asset placement/trust labels such as `accepted`, `staging`, `suspect`, `quarantine`
- identity lifecycle states `active`, `orphan`, `archived`

Operator work roots such as `FIX_ROOT`, `QUARANTINE_ROOT`, and `DISCARD_ROOT` support workflow boundaries. They are not replacements for the v3 identity lifecycle model.

## Validation and Drift Control

Keep architecture and docs aligned with the repo using:

```bash
poetry run python scripts/check_cli_docs_consistency.py
poetry run python scripts/audit_repo_layout.py
make doctor-v3 V3=<V3_DB>
make check-promote-invariant V3=<V3_DB> ROOT=<ROOT> MINUTES=240 STRICT=1
```
