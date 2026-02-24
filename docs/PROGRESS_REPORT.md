# Tagslut Repository - Progress Report

Report Date: February 23, 2026

## Executive Summary
Restructuring phases 0/1/3 are complete. DJ workflow integration is functional for classification and MP3 export, with track-level overrides and crates. The primary remaining risks are the unresolved CLI evacuation (Phase 2), architecture foundations (Phase 4), and incomplete Pioneer finalize automation.

## Completed Work
### Restructuring
- Phase 0: Dedupe eradication.
- Phase 1: Quick wins (scanner move, test renames, pyproject cleanup).
- Phase 3: Decision logic consolidation.

### DJ Integration
- `tagslut/dj` module: curation, export, transcode, key detection.
- Track overrides + crates.
- Scoring classifier + `--promote`.
- `tools/dj_usb_sync.py` orchestrator.

### Housekeeping
- `.gitignore` improvements.
- Script archiving.
- Documentation cleanup.

## Current State
- Tests: 85 passed, 7 skipped.
- Tag hoard: 22,328 rows in `tag_hoard_files` (with `--dump-files`).
- DJUSB MP3s: 423 tracks (~5 GB).
- XLSX input: `DJ_YES.xlsx` (2,988 tracks).

## Pending Work
### High Priority
- Phase 2: CLI evacuation (`cli/main.py` → `cli/commands/*`).
- Phase 4: Architecture foundations (zones module, migrations cleanup, dependency trimming).
- Pioneer finalize automation (ID3v2.3 enforcement, artwork cap, Rekordbox copy).

### DJ Pipeline
- Investigate `dj export` hang.
- Re-run metadata enrich after registration.
- Validate genre key mapping in tag hoard data.
- Implement blocklist manager tool.

## Known Issues
- `cli/main.py` still 113KB.
- `dj export` hang unresolved.
- Tag hoard sample genre fields appear blank.

## Recommended Next Actions
- Re-run enrich: `poetry run python -m tagslut _metadata enrich --db <db> --path "/Volumes/MUSIC/LIBRARY/%" --hoarding --execute`
- Instrument export for hang analysis.
- Implement Pioneer finalize in `tools/dj_usb_sync.py`.
- Build blocklist manager.
