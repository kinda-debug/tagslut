<!-- Status: Active document. Reviewed 2026-03-09. Historical or superseded material belongs in docs/archive/. -->

# Tagslut Repository - Progress Report

Report Date: March 5, 2026

## Executive Summary
Restructuring phases 0/1/2/3 are complete. DJ workflow integration is functional for classification and MP3 export, with track-level overrides, crates, and USB finalize automation. Recent work added a DJ review web app with auto‑verdicts, DJ USB analyzer tooling, and tag sync from file metadata (Lexicon-friendly). Remaining risks are architecture foundations (Phase 4) and ongoing docs consolidation.

## Completed Work
### Restructuring
- Phase 0: Dedupe eradication.
- Phase 1: Quick wins (scanner move, test renames, pyproject cleanup).
- Phase 2: CLI evacuation (`cli/main.py` slimmed; command implementations live in `cli/commands/*`).
- Phase 3: Decision logic consolidation.
- Phase 4: Architecture foundations (zones module, migrations cleanup, dependency trimming).

### DJ Integration
- `tagslut/dj` module: curation, export, transcode, key detection.
- Track overrides + crates.
- Scoring classifier + `--promote`.
- `tools/dj_usb_sync.py` orchestrator.
- Pioneer finalize automation (ID3v2.3, artwork cap, Rekordbox XML) now integrated in `tools/dj_usb_sync.py`.
- DJ Review App: `tools/dj_review_app.py` (OK/Not OK + auto verdict).
- DJ USB Analyzer: `tools/dj_usb_analyzer.py`.
- Tag sync from files: `tools/metadata sync-tags`.

### Housekeeping
- `.gitignore` improvements.
- Script archiving.
- Documentation cleanup.

## Current State
- Tests: not re-run for this report.
- Tag hoard: varies by scan (see `tag_hoard_files` in DB).
- DJUSB MP3 count: depends on current policy + overrides.
- Primary downloader flow is `tools/get <provider-url>`; `tools/get-intake` remains the advanced/backend path.

## Pending Work
### High Priority
- Docs consolidation to final structure.

### DJ Pipeline
- Re-run metadata enrich after registration (as needed).
- Validate genre key mapping in tag hoard data.

## Known Issues
- Tag hoard sample genre fields can be sparse depending on provider coverage.

## Recommended Next Actions
- Re-run enrich: `poetry run tagslut index enrich --db <db> --hoarding --execute`
- Validate the umbrella downloader flow with `tools/get <provider-url> [--dj]`
- Audit tag completeness with `tools/metadata audit-tags`.
