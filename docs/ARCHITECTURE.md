<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

# Architecture

## Active System Shape

`tagslut` is a v3 library-operations system with four main layers:

1. intake and registration
2. identity and metadata management
3. move planning, execution, and provenance
4. downstream DJ export

The active code lives in `tagslut/`, `tools/`, and `scripts/`. Historical code and superseded plans live in `legacy/` and `docs/archive/`.

## Intake Layer

### Normal operator path

Use `tools/get <provider-url>` for day-to-day provider intake. It wraps:

- pre-download filtering
- provider download
- local tag prep
- promote/fix/quarantine/discard planning
- downstream playlist generation
- optional DJ MP3 creation with `--dj`

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

See `docs/CORE_MODEL.md` and `docs/DB_V3_SCHEMA.md` for the table-level contract.

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

There are two active downstream DJ paths.

### Wrapper-driven DJ output

`tools/get --dj` and `tools/get-intake --dj` create DJ MP3s after promote, write DJ playlists, and keep the FLAC master as the source of truth.

### Deterministic v3 DJ pool

The preferred v3 path is:

1. export DJ candidates
2. write DJ profile overlays
3. export DJ-ready rows
4. build the pool with `scripts/dj/build_pool_v3.py`

This path is plan-first and produces deterministic manifests.

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
