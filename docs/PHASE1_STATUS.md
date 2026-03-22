<!-- Status: Active document. Synced 2026-03-22 after Phase 1 PR 11 merge + PR 12 gate update. Historical or superseded material belongs in docs/archive/. -->

# Phase 1 Status

## Phase 1 PR Chain

| # | PR | Status | Branch | Depends On |
| --- | --- | --- | --- | --- |
| 1 | script/layout | SKIP (no-op) | -- | -- |
| 2 | retire dedupe alias | MERGED | -- | -- |
| 3 | recovery tombstone | MERGED | -- | -- |
| 4 | transcoder type/lint | MERGED | -- | -- |
| 5 | flac_scan_prep fix | MERGED | -- | -- |
| 6 | migration scaffold | MERGED | -- | -- |
| 7 | zone/env rename | MERGED | -- | -- |
| 8 | baseline snapshot | MERGED | -- | 2-7 |
| 9 | migration 0006 | MERGED | fix/migration-0006 | 8 |
| 10 | identity service | MERGED | fix/identity-service | 9 |
| 11 | backfill command | MERGED | fix/backfill-v3 | 10 |
| 12 | identity merge | MERGED | (delivered in 195efc7, merged via fix/migration-0006) | 10 |
| 13 | DJ candidate export | MERGED | (delivered in scripts/dj/export_candidates_v3.py + tests/test_export_dj_candidates_v3.py, 8/8 passing) | 11 |
| 14 | docs/AGENT update | NOT STARTED | -- | 13 |
| 15 | Phase 2 seam | NOT STARTED | -- | 14 |

## Current Gate

Stage 5: identity merge - COMPLETE (195efc7).
Current gate: PR 14 (docs/AGENT update). Prompt not yet written.

Status note (2026-03-22):

- PR 9 (migration 0006) merged into dev at commit 5995983.
- PR 10 (identity service) merged into dev at commit 767df22. Validation: all 14 tests passing (5 identity service + 9 transaction boundary).
- PR 10 implementation: exact-match ISRC/provider_id resolution, fuzzy fallback (artist/title/duration with 92% threshold ±2s), single-merge-hop active identity resolution, legacy mirror dual-write, transaction isolation.
- PR 11 (backfill command) merged into dev at commit 1e965b0. Validation: 46 focused backfill/DJ tests passing.
- PR 11 implementation: preserved chosen exact-match winner during V3 backfill, updated stale provenance fixtures for post-0012 `track_identity` inserts, and kept backfill batch transaction behavior intact.
- PR 12 (identity merge) is complete: delivered in 195efc7, merged via fix/migration-0006.
- Use `tools/review/sync_phase1_prs.sh` to push the migration, identity, and DJ-enrichment worktrees without collapsing their PR scope boundaries.

Update this as PRs merge. Codex can read it when needed, and you can reference it in prompts with "check docs/PHASE1_STATUS.md for current state."
