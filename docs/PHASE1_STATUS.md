<!-- Status: Active document. Reviewed 2026-03-09. Historical or superseded material belongs in docs/archive/. -->

## Phase 1 PR Chain

| # | PR | Status | Branch | Depends On |
|---|-----|--------|--------|------------|
| 1 | script/layout | SKIP (no-op) | -- | -- |
| 2 | retire dedupe alias | MERGED | -- | -- |
| 3 | recovery tombstone | MERGED | -- | -- |
| 4 | transcoder type/lint | MERGED | -- | -- |
| 5 | flac_scan_prep fix | MERGED | -- | -- |
| 6 | migration scaffold | MERGED | -- | -- |
| 7 | zone/env rename | MERGED | -- | -- |
| 8 | baseline snapshot | MERGED | -- | 2-7 |
| 9 | migration 0006 | IN PROGRESS | fix/migration-0006 | 8 |
| 10 | identity service | READY | fix/identity-service | 9 |
| 11 | backfill command | READY | fix/backfill-v3 | 10 |
| 12 | identity merge | NOT STARTED | -- | 10 |
| 13 | DJ candidate export | NOT STARTED | -- | 11 |
| 14 | docs/AGENT update | NOT STARTED | -- | 13 |
| 15 | Phase 2 seam | NOT STARTED | -- | 14 |

## Current Gate
Stage 2: migration 0006 is the active blocker.

Status note (2026-03-09):
- `fix/migration-0006` contains `0007_v3_isrc_partial_unique.py` at commit `d853b0a`; the partial unique ISRC behavior was verified in a detached worktree before merge.
- The 6-item action list covering `link_asset_to_identity`, race-safe identity creation, mirror visibility warnings, fuzzy prefiltering, and legacy `library_tracks` verification is complete.
- PR 9 merge remains the gate before PRs 10 (`fix/identity-service`) and 11 (`fix/backfill-v3`) can land.

Update this as PRs merge. Codex can read it when needed, and you can reference it in prompts with "check docs/PHASE1_STATUS.md for current state."
