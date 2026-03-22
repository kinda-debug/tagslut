<!-- Status: Active document. Synced 2026-03-16 after v3 identity hardening phase-closure doc updates. Historical or superseded material belongs in docs/archive/. -->

# REPORT.md - Project Strategy and Current State

## Status

Recovery-era work is complete and archived under `legacy/`. The active project is a v3 music-library operations system with identity-based storage, auditable moves, and downstream DJ outputs.

The current operator surface is stable:

- `tools/get` for normal provider intake
- `tagslut intake/index/decide/execute/verify/report/auth` for canonical CLI work
- `scripts/dj/build_pool_v3.py` and related Make targets for deterministic DJ exports

## Recent Changes Synced In This Review

- Added `tools/review/sync_phase1_prs.sh` to push the current Phase 1 branch stack while preserving PR scope boundaries.
- `tagslut execute move-plan` and `tools/review/move_from_plan.py` now move common track sidecars alongside audio moves.
- `tagslut intake process-root` gained a `dj` phase that can enrich FLAC BPM/key/energy from v3 identity data or Essentia before MP3 transcode.
- `tagslut intake process-root --dry-run` now previews that DJ phase without writing FLAC tags, MP3s, or `dj_pool_path` updates.
- Active root and `docs/` Markdown files were refreshed to match the current v3 surface and to remove stale v2-era guidance.
- V3 identity hardening docs were tightened to match literal migration behavior, and a minimal routine proof target was added: `make check-v3-identity-integrity`.
- Pytest is no longer blocked by the transitive `pylama` plugin autoload (disabled via `pyproject.toml` pytest `addopts`).

## System Shape

### Core data model

- `asset_file`: physical file facts
- `track_identity`: canonical track facts
- `asset_link`: asset-to-identity binding
- `preferred_asset`: deterministic best asset per active identity
- `identity_status`: active/orphan/archived lifecycle state
- `move_plan`, `move_execution`, `provenance_event`: move intent, outcomes, and audit trail

### Intake model

Normal downloads go through `tools/get`, which handles precheck, download, local tag prep, promotion, and optional downstream DJ output.

`tagslut intake process-root` remains useful for already-staged roots, but with an important current constraint:

- on a v3 DB, use `identify,enrich,art,promote,dj`
- `register`, `integrity`, and `hash` are legacy-scan phases and are blocked by the v3 guard

### Move model

Planning and execution are separate by design:

1. generate or review a plan
2. execute with `tagslut execute move-plan`
3. verify with the receipt/parity tooling

Move execution now includes common per-track sidecars, which closes a frequent gap between audio moves and adjacent lyric/artwork files.

### DJ model

DJ outputs are still strictly downstream from the FLAC master library.

There are now two active DJ paths:

- `tools/get --dj` / `tools/get-intake --dj` for normal downstream DJ MP3 creation after promote
- `tagslut intake process-root --phases dj` for staged-root DJ FLAC tag enrichment and MP3 transcode

The v3 builder path remains the preferred deterministic pool export:

```bash
make dj-candidates
make dj-profile-set
make dj-ready
make dj-pool-plan
make dj-pool-run EXECUTE=1
```

## Current Risks and Open Work

- `process-root` still contains legacy-scan phases, so operator docs must continue to distinguish v3-safe usage from legacy scan-only usage.
- DJ metadata quality still depends on provider coverage; Essentia is the fallback when canonical BPM/key are missing.
- The Phase 1 branch stack is still in motion, so branch/PR scope must stay disciplined while migration, identity, backfill, and DJ-enrichment work lands.
- Docs drift remains a real risk because the repo exposes both canonical CLI entry points and compatibility wrappers.

## Near-Term Priorities

1. Keep the Phase 1 stack synchronized and scoped correctly.
2. Prefer the canonical CLI and retire compatibility-only guidance from operator habits.
3. Continue hardening v3-only workflows, especially around staged-root processing and provenance.
4. Keep active docs aligned with command help, repo layout audits, and actual test coverage.
