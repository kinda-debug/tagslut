<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

# AGENT.md - tagslut Repository Guide

## Purpose

`tagslut` manages a FLAC master library with deterministic identity tracking, auditable move execution, and derived DJ outputs.

The master FLAC library is always the source of truth. DJ pools, MP3 exports, playlists, and review artifacts are downstream products.

## Canonical Surface

Use these CLI groups for new work:

- `tagslut intake`
- `tagslut index`
- `tagslut decide`
- `tagslut execute`
- `tagslut verify`
- `tagslut report`
- `tagslut auth`

Specialized but still canonical:

- `tagslut dj`
- `tagslut gig`
- `tagslut export`
- `tagslut init`

Policy-hidden commands such as `canonize`, `enrich-file`, `show-zone`, and `explain-keeper` are implementation details, not the primary operator surface.

## Active Operator Shortcuts

### Primary downloader

Use `tools/get <provider-url>` for normal intake.

- `tools/get --dj` adds downstream DJ MP3 creation and DJ playlists.
- `tools/get --no-hoard` skips the tagging/enrich/art path.
- `tools/get --verbose` prints internal paths, artifacts, and batch snapshots.
- Beatport download flows are tokenless. Do not describe Beatport downloading as requiring tokens.

### Root processing

Use `tagslut intake process-root` when you already have a staged root on disk.

For a v3 DB, the safe phase set is:

```bash
python -m tagslut intake process-root \
  --db <V3_DB> \
  --root <ROOT> \
  --library <MASTER_LIBRARY> \
  --phases identify,enrich,art,promote,dj
```

Important:

- `register`, `integrity`, and `hash` are legacy-scan phases and are blocked by the v3 guard when `--db` points at a v3 database.
- `--dry-run` currently applies to the `dj` phase only. Use `--phases dj --dry-run` to preview DJ FLAC tag enrichment and MP3 transcode without writing files.

### Plan execution

Use `tagslut execute move-plan` for plan CSV execution:

```bash
python -m tagslut execute move-plan \
  --plan plans/example.csv \
  --db <V3_DB> \
  --dry-run
```

Behavior:

- writes move receipts into `move_execution` and `provenance_event`
- keeps move intent in `move_plan`
- moves common per-track sidecars with the audio file when executing
- keeps collision policy as skip, never silent overwrite

Known sidecars:

- `.lrc`
- `.cover.jpg`, `.cover.jpeg`, `.cover.png`
- `.jpg`, `.jpeg`, `.png`

The legacy script `tools/review/move_from_plan.py` still exists for compatibility, but the canonical entry point is `tagslut execute move-plan`.

### DJ pool builder

The deterministic v3 DJ pool builder is `scripts/dj/build_pool_v3.py`, usually through the Make targets documented in `docs/OPERATIONS.md`.

The lightweight staged-root DJ phase also exists inside `tools/review/process_root.py`:

- enriches FLAC BPM/key/energy from v3 identity data when available
- falls back to Essentia for BPM/key/energy when needed
- can preview its work with `--phases dj --dry-run`

## Core Invariants

1. FLAC master library is canonical.
2. Identity truth lives in `track_identity`, not in file paths.
3. Every file move must be auditable.
4. Planning and execution stay separate: `decide -> execute -> verify`.
5. Runtime outputs belong under `artifacts/` or `output/`, not scattered across repo root.
6. Archive and historical docs must live under `docs/archive/`.
7. DJ workflows must not mutate the master library in ways that make it depend on DJ outputs.

## Storage Model

Core v3 ownership:

- `asset_file`: physical file facts
- `track_identity`: canonical track facts
- `asset_link`: asset-to-identity binding
- `preferred_asset`: deterministic preferred asset per identity
- `identity_status`: active/orphan/archived lifecycle state
- `move_plan`, `move_execution`, `provenance_event`: move intent, outcome, and audit truth

If physical state and identity state disagree, trust the owner table for that fact category.

## Work Roots

Current operator work roots are split by intent:

- `FIX_ROOT`: salvageable metadata/tag issues
- `QUARANTINE_ROOT`: risky files needing manual review
- `DISCARD_ROOT`: deterministic duplicates such as `dest_exists`

These roots support operator workflow boundaries. They are not interchangeable with canonical library placement.

## Repository Layout

- `tagslut/`: runtime packages and CLI implementation
- `tools/`: active shell and Python wrappers
- `tools/review/`: legacy-compatible operational helpers and plan generators
- `scripts/`: focused maintenance, audits, migrations, and DJ helpers
- `config/`: policy/configuration inputs
- `docs/`: active documentation
- `docs/archive/`: historical or superseded documentation
- `legacy/`: retired code retained only for reference

## Phase 1 Stack Maintenance

For the current stacked Phase 1 branches, use:

```bash
tools/review/sync_phase1_prs.sh
```

It force-pushes the current migration, identity, and DJ-enrichment worktrees with `--force-with-lease` while keeping PR scope boundaries intact. See `README.md` and `docs/PHASE1_STATUS.md` for the current stack note.

## Documentation Rules

When behavior changes, update the active docs that define operator or developer truth:

- `README.md`
- `REPORT.md`
- `docs/OPERATIONS.md`
- `docs/WORKFLOWS.md`
- `docs/SCRIPT_SURFACE.md`
- `docs/SURFACE_POLICY.md`

If a document is no longer authoritative, archive it instead of leaving stale guidance in `docs/`.

## Quick Checks

Common validation commands:

```bash
poetry run python scripts/check_cli_docs_consistency.py
poetry run python scripts/audit_repo_layout.py
poetry run python -m pytest -q
make doctor-v3 V3=<V3_DB>
make check-promote-invariant V3=<V3_DB> ROOT=<ROOT> MINUTES=240 STRICT=1
```
