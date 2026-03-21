<!-- Status: Active document. Synced 2026-03-22 after ingestion provenance implementation. Historical or superseded material belongs in docs/archive/. -->

# Progress Report

Report date: March 22, 2026

## Session: 2026-03-22 — Ingestion Provenance Migration Implementation

**Task**: Implement the ingestion provenance migration — add four mandatory NOT NULL provenance columns (`ingested_at`, `ingestion_method`, `ingestion_source`, `ingestion_confidence`) to `track_identity`.

**Status**: Completed — all production code, migrations, schema, test fixtures, and enforcement deployed.

**What was implemented**:

1. **4 INSERT surfaces updated** with provenance fields + sensible defaults:
   - `identity_service.py:_identity_value_map()` — primary creation path (defaults: `provider_api`/`high`)
   - `dual_write.py:upsert_track_identity()` — registration UPSERT; provenance excluded from ON CONFLICT UPDATE to preserve immutable `ingested_at`
   - `backfill_identity.py` — backfill path (method: `backfill`, confidence: `high`)
   - `scripts/db/migrate_v2_to_v3.py` — two INSERT blocks (method: `migration`, confidence: `legacy`)

2. **Schema enforcement** (schema version 11 → 12):
   - `schema.py`: 4 NOT NULL columns added to CREATE TABLE, 3 indexes, enforcement trigger `trg_track_identity_provenance_required`, `V3_SCHEMA_VERSION = 12`
   - `0012_ingestion_provenance.py`: ALTER TABLE + backfill (COALESCE from `created_at`) + indexes + trigger + schema_migrations record
   - `supabase/migrations/20260322000000_add_ingestion_provenance.sql`: Postgres equivalent

3. **~28 test files updated** with provenance columns in INSERT fixtures:
   - `conftest.py`: Added `PROV_DEFAULTS`, `PROV_COLS`, `PROV_VALS` constants
   - All test files using `create_schema_v3()` updated with provenance in their INSERTs
   - Tests using legacy `init_db()` or custom minimal schemas correctly left unchanged

4. **13 new enforcement tests** in `tests/storage/v3/test_migration_0012.py`:
   - `TestMigration0012Upgrade`: columns added, backfill, indexes, trigger, migration record, idempotent
   - `TestProvenanceEnforcement`: success case, 4 missing-field rejections, empty-string trigger, empty source allowed

5. **Docs**: `DB_V3_SCHEMA.md` updated with provenance fields and sync date

**Test results**: `poetry run pytest tests/ → 934 passed, 21 failed`
- All 21 failures are **pre-existing** (verified by stash comparison against HEAD):
  - 10× `test_merge_identities_by_beatport_v3` — UNIQUE constraint on `beatport_id` (v11 schema, test data predates constraint)
  - 5× `test_tidal_beatport_enrichment` — `search_by_isrc` API change
  - 3× `test_report_identity_qa_v3` — same UNIQUE constraint
  - 1× `test_migrate_v2_to_v3` — assertion on `spotify_id`
  - 1× `test_backfill_identity_v3` — UNIQUE constraint
  - 1× `test_plan_fpcalc` — ordering-dependent flake
- **Zero regressions** from this change

**Files changed** (production):
- `tagslut/storage/v3/schema.py`
- `tagslut/storage/v3/identity_service.py`
- `tagslut/storage/v3/dual_write.py`
- `tagslut/storage/v3/backfill_identity.py`
- `scripts/db/migrate_v2_to_v3.py`
- `tagslut/storage/v3/migrations/0012_ingestion_provenance.py` (new)
- `supabase/migrations/20260322000000_add_ingestion_provenance.sql` (new)

**Files changed** (tests): `tests/conftest.py` + ~27 test files with INSERT fixture updates + `tests/storage/v3/test_migration_0012.py` (new)

**Files changed** (docs): `docs/DB_V3_SCHEMA.md`, `docs/PROGRESS_REPORT.md`

---

## Session: 2026-03-21 (pass 2) — Ingestion Provenance Memo Correction

**Task**: Revise the ingestion provenance execution memo to align with `PROJECT_DIRECTIVES.md`.

**Status**: Completed — memo corrected. No code changes made. Analysis/spec pass.

**What was verified**:

1. Prior memo incorrectly concluded `ingestion_source` should remain nullable. `PROJECT_DIRECTIVES.md` line 48 is unambiguous: "These are NOT NULL. Any migration or insert that omits them is wrong." The weaker interpretation from `INGESTION_PROVENANCE.md` line 173 (which only named two fields in enforcement prose) is overridden.

2. All four fields must be NOT NULL and enforced in both fresh-DB DDL (`schema.py`) and migration path (trigger in `0012`).

3. Concrete fallback values specified for every insert surface — no operator judgment required. L1/L2 derive source from available provider context; L3 uses download_source; L4/M1/M2 use `'migration'`/`'legacy'` with descriptive source strings.

4. Both prior "blocking ambiguities" resolve as implementation decisions. No operator input needed on either.

5. Implementation ordering corrected: code updates and test fixture updates must precede schema enforcement (NOT NULL + trigger). The prior memo had schema first — that breaks all test fixtures before callers are fixed.

6. Test fixture scope acknowledged: ~25 test files INSERT into track_identity without provenance. These require updates as part of this migration. A `conftest.py` helper reduces churn.

7. `schema.py` must have NOT NULL with no DEFAULT on all four columns. A DEFAULT sentinel silently accepts incomplete inserts.

8. The enforcement trigger must live in both `schema.py` and `0012_ingestion_provenance.py` to prevent fresh-DB vs migration-path drift.

**Files changed**: `docs/PROGRESS_REPORT.md` (this update only).

**Tests run**: None (no code changes).

**Next steps**:

- Revised memo is ready for Codex. 11-step implementation sequence.
- No operator decisions remain open.
- Run target after implementation: `poetry run pytest tests/storage/v3/test_migration_0012.py tests/storage/v3/test_ingestion_provenance_inserts.py -v`
- After implementation: update `docs/ROADMAP.md` §14 to reference both migration file paths.

---

## Session: 2026-03-21 — Ingestion Provenance Migration — Spec / Execution Memo

**Task**: Produce an implementation-grade execution memo for the ingestion provenance migration (`ingested_at`, `ingestion_method`, `ingestion_source`, `ingestion_confidence` on `track_identity`).

**Status**: Completed — Analysis and spec pass. No code changes made. Memo is ready for Codex.

**What was verified**:
1. All four provenance fields are absent from every schema surface and every production insert path — confirmed by grep across full Python source and both schema files (`schema.py`, `supabase/migrations/20260315154756_tagslut_schema.sql`).
2. Five insert surfaces identified (3 live, 2 legacy bridge):
   - L1/L2: `identity_service.py:_create_identity()` via `_identity_value_map()` — primary creation path
   - L3: `dual_write.py:upsert_track_identity()` — registration path (no provenance params)
   - L4: `backfill_identity.py:_resolve_identity_via_service()` — live backfill caller with hardcoded partial provenance dict
   - M1/M2: `scripts/db/migrate_v2_to_v3.py` — two INSERT blocks, legacy one-time bridge
3. Two migration paths required: `tagslut/storage/v3/migrations/0012_ingestion_provenance.py` (SQLite) + `supabase/migrations/20260322000000_add_ingestion_provenance.sql` (Postgres). ROADMAP §14 incorrectly names only `supabase/migrations/` — this mismatch is called out in the memo.
4. Six doc/schema inconsistencies documented: nullable-vs-NOT NULL conflict in INGESTION_PROVENANCE.md, missing ROADMAP migration dir, `ingestion_source` NOT NULL overstated in PROJECT_DIRECTIVES.md, DB_V3_SCHEMA.md missing all 4 columns, `_merge_identity_fields_if_empty()` provenance-overwrite risk, `dual_write.py` ON CONFLICT semantics for `ingested_at`.
5. Two blocking operator decisions identified: default `ingestion_method` for empty provenance dict, and whether `create_schema_v3()` should co-locate the enforcement trigger.

**Files changed**: None (analysis/spec pass only).

**Tests run**: None (no code changes).

**Next steps**:
- Operator must resolve two blocking ambiguities (see memo §9) before handing to Codex.
- Codex implementation sequence: 9 commits, schema first (steps 1–3), then service layer (4–7), then docs+tests (8–9).
- Targeted test run after implementation: `poetry run pytest tests/storage/v3/test_migration_0012.py tests/storage/v3/test_ingestion_provenance_inserts.py -v`
- After migration lands: update ROADMAP §14 to reference both migration file paths.

---

## Session: 2026-03-21 — Resume-Refresh Fix Implementation Verification

**Task**: Verify implementation of `resume-refresh-fix` spec to fix `--resume` mode for enrichment, DJ export, and clean run summaries.

**Status**: Completed — All three root causes verified as already implemented and passing all tests.

**What was verified**:
1. **Root Cause 1**: PROMOTED_FLACS_FILE supplemented from batch root in resume mode (lines 2513-2523 of tools/get-intake) ✅
2. **Root Cause 2**: DJ export fallback wired to precheck inventory in resume mode (lines 2619-2657) ✅
3. **Root Cause 3**: Spurious dest_exists discard plan suppressed in resume mode (lines 2340-2352) ✅

**Tests run**: `poetry run pytest tests/exec/test_resume_refresh.py -v` — **7/7 PASSED**

**Related commits**:
- 730d2b1 (Mar 18): fix(intake): suppress dest_exists discard plan in resume mode
- 2fb2a50 (Mar 18): fix(intake): supplement promoted file lists from batch root in resume mode
- 3f3f37d (Mar 18): fix(intake): wire DJ export fallback to inventory in resume mode
- bf3df38 (Mar 18): test(intake): add resume mode unit tests for supplement, enrichment, discard suppression
- 0a98453 (Mar 21): chore: fix gitignore, add copilot instructions and resume-refresh prompt (specification added)

**Outcome**: No code changes needed — implementation complete, tested, and verified. Created PROGRESS_REPORT.md documentation of verification findings (committed as 79cd387).

---

## Previous Report

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
