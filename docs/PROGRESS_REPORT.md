<!-- Status: Active document. Synced 2026-03-14 after DJ pipeline migration + Lexicon backfill. Historical or superseded material belongs in docs/archive/. -->

# Progress Report

Report date: March 14, 2026

## Executive Summary

The v3 core surface is active. Today's session completed the DJ pipeline schema migration (0010), executed a full Lexicon DJ → track_identity metadata backfill, and archived the stale `PHASE5_LEGACY_DECOMMISSION.md` stub from active docs. The `reconcile_log` table is now populated and the `lexicon_*` payload keys are live on 20,517 identities.

## Recent Completed Work (2026-03-14)

- Applied migration `0009_add_mp3_dj_tables.sql` + `0010_add_dj_pipeline_tables.sql` to `music_v3.db` (7 DJ pipeline tables now in `sqlite_master`; checkpoint at `data/checkpoints/reconcile_schema_0010.json`).
- Wrote and ran `tagslut/dj/reconcile/lexicon_backfill.py`: joined `/Volumes/MUSIC/lexicondj.db` against `track_identity` via normalized text matching.
  - 20,517 identities enriched with `lexicon_energy`, `lexicon_danceability`, `lexicon_happiness`, `lexicon_popularity` in `canonical_payload_json`.
  - 2,657 identities gained `lexicon_bpm` (where `canonical_bpm` was NULL).
  - 29,442 rows written to `reconcile_log` (20,517 `backfill_metadata` + 8,925 `backfill_tempomarkers`).
  - 11,679 identities unmatched (36% of library — tracks not present in Lexicon).
- Fixed double-counting stats bug in `lexicon_backfill.py`.
- Archived `docs/PHASE5_LEGACY_DECOMMISSION.md` stub (active copy was a redirect-only stub; full content already in `docs/archive/`).
- Updated `REDESIGN_TRACKER.md`, `DJ_WORKFLOW.md`, `DB_V3_SCHEMA.md` to reflect backfill completion.

## Previous Completed Work (2026-03-09)

- Added `tools/review/sync_phase1_prs.sh` for the active Phase 1 branch stack.
- Added common sidecar handling to move-plan execution.
- Added staged-root DJ FLAC tag enrichment and MP3 transcode hooks to `process-root`.
- Added `process-root --dry-run` support for previewing the DJ phase.
- Refreshed active root/docs Markdown files so examples match the current v3 guardrails.

## Current State

- Tests: 579 passed, 2 failed, 1 warning (last run March 8, 2026 — recheck after today's new module).
- `reconcile_log`: 29,442 rows from run `4efccd9c2f3c46089d3be775e14999b2`.
- `track_identity` rows with Lexicon energy  15,881 / 32,196 (49%).
- `dj_admission`, `mp3_asset`: populated by migration; admission backfill not yet run.
- Primary downloader flow remains `tools/get <provider-url>`; `tools/get-intake` remains the advanced/backend path.
- Canonical CLI surface remains `tagslut intake/index/decide/execute/verify/report/auth/dj`.
- The deterministic v3 DJ pool path remains the preferred builder/export route.

## Risks

- Compatibility wrappers still exist, so stale operator habits can reintroduce drift.
- Provider metadata coverage is uneven, which keeps fallback/repair workflows important.
- The Phase 1 stacked branches still need careful scope control while landing.
- Lexicon text matching has no streaming-ID fallback (beatport/spotify IDs absent from Lexicon DB); 36% of identities remain unmatched.

## Recommended Next Actions

1. Run `tagslut dj backfill --db "$TAGSLUT_DB"` to populate `dj_admission` from existing `mp3_asset` rows.
2. Run `python -m tagslut.dj.reconcile.lexicon_backfill --dry-run` after any Lexicon DB update to preview incremental changes.
3. Keep the Phase 1 stack synchronized with `tools/review/sync_phase1_prs.sh`.
4. Prefer `tagslut execute move-plan` over compatibility executors for reviewed plans.
5. Continue running the doc/layout consistency checks after behavior changes.
