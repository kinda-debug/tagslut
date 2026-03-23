# tagslut — Action Plan

<!-- Generated: 2026-03-23 by repo-audit-and-plan.prompt.md, patched same day -->
<!-- Status: Active. Supersedes ROADMAP.md for action sequencing. Update as items complete. -->
<!-- ROADMAP.md remains the historical record and agent contract reference. -->

### 1. DB state summary

Current row counts, migration level, confirmed FRESH DB path, confirmed symlink status.

- Confirmed FRESH DB path: `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`
- Symlink trap status: `ls -la /Users/georgeskhawam/Projects/tagslut_db/music_v3.db` -> `No such file or directory`
- Row counts (FRESH DB):
  - `asset_file`: 25534
  - `mp3_asset`: 1
  - `dj_playlist`: 0
  - `reconcile_log`: 27163
- `track_identity` ingestion distribution (FRESH DB): `provider_api | high | 188`
- Migration level:
  - `schema_migrations` latest applied: v3 migration 12 (`0012_ingestion_provenance.py`) as of 2026-03-22
  - Migration 0014 (`0014_dj_validation_state.py`) exists in source but was not reflected in the DB query — verify with `sqlite3 FRESH_DB "SELECT * FROM schema_migrations ORDER BY applied_at DESC LIMIT 5;"`
  - Migration 0013 (five-tier confidence CHECK) is recorded as included in 0012 per ROADMAP §16

### 2. Prompt file audit

For every file in `.github/prompts/`:
  | prompt file | status | blocker / notes |

| prompt file | status | blocker / notes |
|---|---|---|
| `.github/prompts/bpdl-cover-fix.prompt.md` | BLOCKED | Requires mounted `/Volumes/MUSIC/mdl/bpdl`; filesystem-only operator run; writes manifest to external volume. |
| `.github/prompts/credential-consolidation-phase1.prompt.md` | COMPLETE | Beatport token precedence + warnings present in `tagslut/metadata/providers/beatport.py`; `tagslut auth token-get` exists in `tagslut/cli/commands/auth.py`. |
| `.github/prompts/dj-ffmpeg-validation.prompt.md` | COMPLETE | Roadmap marks complete (commit `de59b4f`). |
| `.github/prompts/dj-missing-tests-week1.prompt.md` | COMPLETE | Roadmap marks complete (commit `fea8f2e`). |
| `.github/prompts/dj-pipeline-hardening.prompt.md` | READY | Roadmap marks as active follow-up (§3.1). |
| `.github/prompts/dj-validate-gate.prompt.md` | COMPLETE | Migration `tagslut/storage/v3/migrations/0014_dj_validation_state.py` exists; roadmap §3.4 marked closed. |
| `.github/prompts/dj-workflow-audit.prompt.md` | COMPLETE | Roadmap marks complete (commit `16ee5ca`). |
| `.github/prompts/fix-backfill-conflicts-fixture.prompt.md` | COMPLETE | Fixture insert includes provenance columns in `tests/storage/v3/test_plan_backfill_identity_conflicts_v3.py`. |
| `.github/prompts/fix-get-forward-args.prompt.md` | COMPLETE | Roadmap §1 “Resume/refresh fix” marked complete (commits `730d2b1`, `2fb2a50`, `3f3f37d`, `bf3df38`). |
| `.github/prompts/fix-precheck-v3-schema.prompt.md` | COMPLETE | Phase 1 chain complete; schema/provenance enforcement already landed. |
| `.github/prompts/intake-pipeline-hardening.prompt.md` | STALE | Roadmap says already implemented on dev (no patch needed). Archive prompt (don’t run). |
| `.github/prompts/lexicon-reconcile.prompt.md` | COMPLETE | Lexicon import + reconcile-scan surfaced in CLI (commit `03f2310`). |
| `.github/prompts/migration-0012-provenance.prompt.md` | COMPLETE | Migration present (`0012_ingestion_provenance.py`); DB shows it applied as v3 migration 12. |
| `.github/prompts/open-streams-post-0010.prompt.md` | READY | Use for remaining “open streams” work; keep strictly off `artifacts/`, `output/`, generated SDKs, and `docs/archive/`. |
| `.github/prompts/phase1-pr10-identity-service.prompt.md` | COMPLETE | Roadmap PR10 marked complete (commit `767df22`). |
| `.github/prompts/phase1-pr12-identity-merge.prompt.md` | COMPLETE | Roadmap PR12 marked complete (`195efc7`, delivered via migration-0006 stream). |
| `.github/prompts/phase1-pr14-agent-docs-update.prompt.md` | COMPLETE | Roadmap PR14 marked complete (commit `8a0b00d`). |
| `.github/prompts/phase1-pr15-phase2-seam.prompt.md` | COMPLETE | Roadmap PR15 marked complete (commit `d992d20`). |
| `.github/prompts/phase1-pr9-migration-0006-merge.prompt.md` | COMPLETE | Roadmap PR9 marked complete (commit `5995983`). |
| `.github/prompts/postman-api-optimize.prompt.md` | STALE | Not part of current operator surface; risks touching generated SDKs under `postman/`. Archive prompt (don’t run). |
| `.github/prompts/repo-audit-and-plan.prompt.md` | COMPLETE | This audit produced `docs/ACTION_PLAN.md`. |
| `.github/prompts/repo-cleanup.prompt.md` | COMPLETE | Roadmap cleanup marked complete; recent log includes cleanup commits (e.g. `ab9644f`, `519e1bf`). |
| `.github/prompts/resume-refresh-fix.prompt.md` | COMPLETE | Roadmap §1 marked complete (commits listed in Roadmap). |

### 3. Open work — ranked by execution order

Every open item from ROADMAP.md, REDESIGN_TRACKER.md open streams, audit docs, and anything discovered during source read.

## 1. Unblock pytest collection (missing `tools.dj_usb_analyzer`)
**Status**: UNBLOCKED  
**Agent**: Codex  
**Prompt**: needs authoring  
**Depends on**: nothing  
**Done when**: `poetry run pytest tests/ --co -q` collects with 0 errors (collection-only)  
**Notes**: Current snapshot: `1064 tests collected, 1 error` with `ModuleNotFoundError: No module named 'tools.dj_usb_analyzer'` in `tests/tools/test_dj_usb_analyzer.py`.

## 2. DJ pipeline hardening follow-up (§3.1)
**Status**: UNBLOCKED  
**Agent**: Codex  
**Prompt**: `.github/prompts/dj-pipeline-hardening.prompt.md`  
**Depends on**: nothing  
**Done when**: prompt-defined acceptance criteria met and targeted DJ test slice passes (per prompt)  
**Notes**: Roadmap indicates this is the active follow-up after audit + validation gate + ffmpeg validation.

## 3. Pool-wizard transcode path live verification (open stream)
**Status**: OPERATOR-ONLY  
**Agent**: Operator  
**Prompt**: needs authoring  
**Depends on**: 2  
**Done when**: one representative run exercises the transcode execution path where a candidate has `identity_id` but no reusable MP3 source, producing audited artifacts and validated MP3 output  
**Notes**: Open stream explicitly called out in `docs/REDESIGN_TRACKER.md`. Requires real/dev DB state or a disposable fixture DB.

## 4. Remove legacy wrappers (open stream)
**Status**: NEEDS-DESIGN  
**Agent**: Claude Code  
**Prompt**: needs authoring  
**Depends on**: 2  
**Done when**: internal callers are audited and wrapper families are removed or gated, with canonical replacements documented and still stable  
**Notes**: Open stream in `docs/REDESIGN_TRACKER.md` and decommission sequencing in `docs/PHASE5_LEGACY_DECOMMISSION.md`.

## 5. `process-root` phase contract documentation (open stream)
**Status**: NEEDS-DESIGN  
**Agent**: Claude Code  
**Prompt**: needs authoring  
**Depends on**: nothing  
**Done when**: `docs/WORKFLOWS.md` includes concise per-phase input/output contracts for `identify, enrich, art, promote, dj` (v3-safe phase set), matching current code surface  
**Notes**: Open stream in `docs/REDESIGN_TRACKER.md`; keep it short and operational (no history).

## 6. Decide and document provider-repair asymmetry (Beatport-only vs generic)
**Status**: NEEDS-DESIGN  
**Agent**: Claude Code  
**Prompt**: needs authoring  
**Depends on**: nothing  
**Done when**: architecture + ops docs explicitly state whether non-Beatport duplicate remediation is manual-only or supported by generic tooling; if tooling is desired, it’s scoped with acceptance tests and migration-safety constraints  
**Notes**: Called out as the “main remaining technical gap” in the v3 identity hardening plan embedded in `docs/ROADMAP.md`.

## 7. Outer-transaction boundary proof tests for v3 write paths
**Status**: BLOCKED  
**Agent**: Codex  
**Prompt**: needs authoring  
**Depends on**: 6  
**Done when**: tests prove rollback behavior both when functions own the transaction and when called under an outer transaction, for the listed write paths in v3 identity hardening notes  
**Notes**: Next proof slice in the v3 identity hardening plan embedded in `docs/ROADMAP.md`.

## 8. Align migration audit wording with literal SQL behavior (0010/0011)
**Status**: NEEDS-DESIGN  
**Agent**: Claude Code  
**Prompt**: needs authoring  
**Depends on**: nothing  
**Done when**: docs describing 0010/0011 uniqueness/audit behavior match actual SQL (or SQL is adjusted to match docs), with a targeted verification gate  
**Notes**: Explicit doc/code alignment slice in the v3 identity hardening plan embedded in `docs/ROADMAP.md`.

## 9. Formalize long-term policy for `itunes_id` + `musicbrainz_id`
**Status**: NEEDS-DESIGN  
**Agent**: Claude Code  
**Prompt**: needs authoring  
**Depends on**: nothing  
**Done when**: docs state whether these remain policy-only identifiers or become schema-enforced; if enforced, the migration + repair strategy is explicit  
**Notes**: Explicit policy slice in the v3 identity hardening plan embedded in `docs/ROADMAP.md`.

## 10. Decide and document `merged_into_id` cycle posture
**Status**: NEEDS-DESIGN  
**Agent**: Claude Code  
**Prompt**: needs authoring  
**Depends on**: nothing  
**Done when**: docs explicitly state whether runtime-only cycle detection is the intended protection, or whether stronger prevention is required, with a proof obligation either way  
**Notes**: Explicit resilience slice in the v3 identity hardening plan embedded in `docs/ROADMAP.md`.

### 4. Items confirmed complete — do not reopen

- Resume/refresh fix (ROADMAP §1) — commits `730d2b1`, `2fb2a50`, `3f3f37d`, `bf3df38`.
- Ingestion provenance migration 0012 — applied in FRESH DB; present as `schema_migrations` v3 `12` (`0012_ingestion_provenance.py`).
- Provider uniqueness hardening (0010/0011) — present in FRESH DB as `schema_migrations` v3 `10` and `11`.
- DJ workflow audit — ROADMAP §3.2 marks complete (commit `16ee5ca`).
- FFmpeg output validation — ROADMAP §3.3 marks complete (commit `de59b4f`).
- DJ Week 1 missing tests — recent log includes completion (commit `fea8f2e`).

### 5. Operator-only checklist

- Run any prompt that touches mounted media volumes under `/Volumes/MUSIC/...` (e.g. `bpdl-cover-fix`) and review manifests before deletions.
- Run any task that depends on a real “live cohort” DB or real library content (pool-wizard transcode live verification).
- Archive STALE prompts (do not run them).
- Verify any `--db` path before running commands (see DB rules below).

### 6. DB path safety rules (permanent)

Canonical path for FRESH DB. Explicitly state that the symlink at tagslut_db/music_v3.db is gone and must never be recreated. Any agent that sees a --db argument pointing at a path without FRESH_2026 in it must stop and verify before proceeding.

- Canonical FRESH DB path: `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`
- Symlink trap: `/Users/georgeskhawam/Projects/tagslut_db/music_v3.db` is gone and must never be recreated.
- Stop rule: any `--db` path without `FRESH_2026` must be verified before proceeding.

### 7. Known Codex failure patterns observed in this repo

Patterns where Codex has produced bugs before. Each entry: what went wrong, what the correct behaviour is, what to check in review.

- **Invented schema columns** (2026-03-23): `mp3_build.py` and `master_scan.py` stub inserts used `source` and `status` columns that don't exist in `track_identity`. Correct behavior: always check `PRAGMA table_info(track_identity)` before writing any INSERT. Required columns: `ingested_at`, `ingestion_method`, `ingestion_source`, `ingestion_confidence` (all NOT NULL, no DEFAULT). Review gate: run a reconcile-scan dry-run after delivery and confirm 0 errors before accepting.
- **Symlink/stale DB path routing** (2026-03-23): Codex resolved `tagslut_db/music_v3.db` through the now-deleted symlink to the LEGACY DB. In one sub-run it also queried `EPOCH_2026-03-04/music_v3.db` (renamed path) before falling back. Correct behavior: use only `FRESH_2026/music_v3.db`. Review gate: grep all `--db` args in generated code and session output for paths not containing `FRESH_2026`.
- **Over-scanning into excluded directories**: session reconnaissance reads from `artifacts/`, `output/`, `docs/archive/`, or `postman/sdks/` — all thousands of timestamped run files that blow context without providing useful information. Correct behavior: skip these directories entirely. Review gate: confirm no reads from excluded paths in session trace.
- **Schema edits without migrations**: direct edits to `tagslut/storage/v3/schema.py` without a corresponding migration file. Correct behavior: migration-first, schema.py second, then verify schema equivalence. Review gate: any schema.py diff must have a matching migration file in the same commit.
- **Broken pytest collection**: adding tests that import non-existent modules. Correct behavior: keep `poetry run pytest tests/ --co -q` collecting with 0 errors. Review gate: always run collect-only after adding new test files.
- **Executing `--execute` commands before dry-run verification**: running write paths directly without a dry-run check first. Correct behavior: always dry-run, review output, then execute. Review gate: `--execute` flags must not appear in a session's first command for any given pipeline step.
