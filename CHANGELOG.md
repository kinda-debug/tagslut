# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

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
- OneTagger ISRC enrichment wrappers (tools/tag, tools/tag-build, tools/tag-run)
- Classification v2: genre fallback + soft scoring (scripts/classify_tracks_sqlite.py)

### Changed
- Version bumped from 2.0.0 to 3.0.0
- Project description updated to management-first framing

### Removed
- Legacy CLI wrappers: scan, recommend, apply, promote, quarantine, mgmt, metadata, recover (retired per Phase 5)
- Recovery-era framing and documentation

## [2.0.0] — 2025-02-01
### Changed
- Rebrand from dedupe to tagslut
- Recovery phase declared complete; library rebuilt
