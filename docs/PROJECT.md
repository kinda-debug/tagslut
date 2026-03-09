<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

# Project

## Summary

`tagslut` is a Python-based operations system for a large FLAC music library with a downstream DJ workflow.

The project goal is not generic media management. It is a deterministic, auditable pipeline that:

- keeps one canonical FLAC master library
- resolves canonical track identity across providers and file variants
- executes guarded file moves with receipts and provenance
- derives DJ-facing MP3 outputs and playlists without making them authoritative

## Active Product Surface

Canonical CLI groups:

- `tagslut intake`
- `tagslut index`
- `tagslut decide`
- `tagslut execute`
- `tagslut verify`
- `tagslut report`
- `tagslut auth`

Specialized CLI groups:

- `tagslut dj`
- `tagslut gig`
- `tagslut export`
- `tagslut init`

Primary wrapper:

- `tools/get <provider-url>`

## Current Architecture Priorities

### 1. Keep v3 ownership boundaries clean

- physical facts belong to `asset_file`
- canonical identity facts belong to `track_identity`
- move truth belongs to `move_plan`, `move_execution`, and `provenance_event`

### 2. Keep operator flows deterministic

- prefer plan-first workflows
- keep collision policy conservative
- verify promotion invariants after move workflows

### 3. Keep DJ output downstream-only

- master FLAC library remains authoritative
- DJ MP3s, playlists, and USB exports stay derivable
- staged-root DJ enrichment is allowed, but the v3 builder remains the preferred deterministic export path

## Current State

- recovery-era implementation is archived under `legacy/`
- root/docs Markdown surface was refreshed on 2026-03-09 to match the live code
- Phase 1 branch stack is still active, with a dedicated helper for synchronized pushes: `tools/review/sync_phase1_prs.sh`
- `tagslut execute move-plan` is the canonical move-plan executor
- `tagslut intake process-root` now supports a DJ-only preview path via `--phases dj --dry-run`

## Constraints

- FLAC master library is large enough that manual-only curation does not scale
- provider metadata coverage is uneven; fallback logic is required
- DJ hardware and software consume derived MP3 outputs, not the master FLACs
- historical wrappers still exist, so docs drift is a real operational risk if not policed

## Near-Term Work

1. Land the remaining Phase 1 stack cleanly.
2. Keep active docs aligned with the canonical CLI surface.
3. Continue tightening v3-only paths so staged-root workflows do not imply legacy-scan behavior.
4. Improve metadata completeness where provider coverage is sparse.
