<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

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
| 9 | migration 0006 | MERGED | fix/migration-0006 | 8 |
| 10 | identity service | IN PROGRESS | fix/identity-service | 9 |
| 11 | backfill command | READY | fix/backfill-v3 | 10 |
| 12 | identity merge | NOT STARTED | -- | 10 |
| 13 | DJ candidate export | NOT STARTED | -- | 11 |
| 14 | docs/AGENT update | NOT STARTED | -- | 13 |
| 15 | Phase 2 seam | NOT STARTED | -- | 14 |

## Current Gate

Stage 3: identity service is the active blocker.

Status note (2026-03-22):

- PR 9 (migration 0006) merged into dev at commit 5995983.
- PR 9 validation: 2/2 migration tests, 6/6 migration runner, 9/9 transaction boundary tests all passing.
- PR 9 work included: merge-lineage assertions enforcement, legacy mirror sync on merge, ISRC copy-on-blank during merge.
- PR 10 (`fix/identity-service`) is now the active gate. Branch synced clean from dev at commit f091b01.
- Use `tools/review/sync_phase1_prs.sh` to push the migration, identity, and DJ-enrichment worktrees without collapsing their PR scope boundaries.

Update this as PRs merge. Codex can read it when needed, and you can reference it in prompts with "check docs/PHASE1_STATUS.md for current state."
