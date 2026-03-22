<!-- Status: Active document. Synced 2026-03-22 after migration 0012 complete. Historical or superseded material belongs in docs/archive/. -->

# Progress Report

Report date: March 22, 2026

## Session: 2026-03-22 — Migration 0012: Ingestion Provenance Complete

**Task**: Close all remaining gaps in migration 0012 — legacy init_db path,
test fixtures, CHECK constraints, and documentation.

**Status**: Completed — commit `bef5931`, 6 files changed, 16 tests passing.

**What was done**:

1. **`_ensure_v3_schema` (legacy init_db path)** — added 4 provenance columns
   via `_add_missing_columns`, 3 provenance indexes, and the enforcement trigger
   `trg_track_identity_provenance_required`. All three DB creation paths now
   enforce provenance.

2. **`create_schema_v3` CHECK constraints** — added vocabulary CHECK constraints
   for `ingestion_method` (8 values) and `ingestion_confidence` (5 tiers) at
   the column definition level for fresh DBs.

3. **Postgres migration** — `20260322100000_confidence_tier_check.sql` adds both
   CHECK constraints to the Postgres `track_identity` table.

4. **Test fixtures** — updated 3 files:
   - `test_dj_pipeline.py` — imported PROV_COLS/PROV_VALS, updated `_insert_identity`
   - `test_track_db_sync.py` — added provenance columns to inline schema + 3 INSERTs,
     fixed off-by-one placeholder bug
   - `test_verify_v3_migration.py` and `test_migration_report_v2_to_v3.py` — verified
     (migration report uses ad-hoc schema, left as-is per decision rule)

5. **`docs/DB_V3_SCHEMA.md`** — provenance section updated from "pending" to complete,
   vocabulary tables added for both confidence tiers and method values, trigger
   enforcement strategy documented.

**Tests run**: 16 targeted tests across 6 files — ALL PASS.

**Next**: Migration 0013 (five-tier CHECK constraint, already covered by 0012),
then fresh DB initialization.

---

## Session: 2026-03-21 (pass 8) — TIDAL OAuth Refactor

**Status**: Completed — commit `3a3595c`, 1 file, net −59 lines.
Global mutable state removed, monotonic clock, private naming, docstring restored.
No behaviour changes.

---

## Session: 2026-03-21 (pass 7) — Postman Collection-Level Token Guard

**Status**: Completed — commit `14c9e29`. Postman agent track fully complete.
Token guard at `tagslut - Beatport API/.resources/definition.yaml`.

---

## Session: 2026-03-21 (pass 6) — Postman Validation Run + Spotify Chain

**Status**: Completed — commit `37619ae`, 4 new files, 290 insertions.
`5c` Spotify cross-check, Validation Run folder `6a → 6b → 5a → 5b → 5c`.

---

## Session: 2026-03-21 (pass 5) — Postman API Collection + Multi-Provider ID Policy

**Status**: Completed — commit `6ab432b`, 6 files, 276 insertions, 57 deletions.
Collection cleanup, ISRC auth, Track by ID validation, Identity Verification chain,
multi-provider ID policy, five-tier confidence model, tiddl config documented.

---

## Session: 2026-03-21 (pass 4) — Repo Cleanup, DB Epoch Management, Context Bundle

**Status**: Completed. Epoch renamed, backups pruned, artifacts archived to SAD,
sensitive files deleted, DB symlink added, PROJECT_DIRECTIVES.md, ROADMAP revised.

---

## Session: 2026-03-21 (pass 3) — Ingestion Provenance Standard

**Status**: Completed. INGESTION_PROVENANCE.md, CORE_MODEL Rules 6–7, ROADMAP §14.
Four-tier model — superseded by pass 5 five-tier revision.

---

## Session: 2026-03-21 (pass 2) — Ingestion Provenance Memo Correction

**Status**: Completed. All four fields NOT NULL no DEFAULT confirmed.
Implementation ordering corrected. ~25 test fixtures require updates.

---

## Session: 2026-03-21 (pass 1) — Ingestion Provenance Migration Spec

**Status**: Completed. Five insert surfaces, two migration paths, six inconsistencies
documented. Memo ready for Codex.

---

## Session: 2026-03-21 — Resume-Refresh Fix Verification

**Status**: Completed. `poetry run pytest tests/exec/test_resume_refresh.py -v` — **7/7 PASSED**
Commits: 730d2b1, 2fb2a50, 3f3f37d, bf3df38, 0a98453

---

## Previous Report — 2026-03-14

v3 core surface active. DJ pipeline migration (0010) applied, Lexicon backfill complete.
20,517 identities enriched, 11,679 unmatched (36%). Tests: 579 passed, 2 failed (March 8 baseline).
