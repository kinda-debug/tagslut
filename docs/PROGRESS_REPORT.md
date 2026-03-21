<!-- Status: Active document. Synced 2026-03-21 after Postman Validation Run + Spotify chain. Historical or superseded material belongs in docs/archive/. -->

# Progress Report

Report date: March 21, 2026

## Session: 2026-03-21 (pass 6) — Postman Validation Run + Spotify Chain

**Task**: Build Validation Run folder and Spotify ISRC cross-check (tasks 6 + 7).

**Status**: Completed — commit `37619ae`, 4 new files, 290 insertions.

**What was done**:

1. **`5c` Spotify ISRC cross-check** — queries Spotify search by ISRC, compares
   `external_ids.isrc`, logs `SPOTIFY CORROBORATED`, `CONFLICT`, or `NOT FOUND`.
   Sets `spotify_verified_id` in environment. Three-way agreement (Beatport + TIDAL
   + Spotify) maps to `ingestion_confidence = 'corroborated'` per `MULTI_PROVIDER_ID_POLICY.md`.

2. **Validation Run folder** — three requests for end-to-end chain validation:
   - `6a`: TIDAL album → picks first track → seeds `beatport_test_isrc` + `tidal_seed_isrc`
   - `6b`: Beatport Track by ID → validates 9 canonical fields → ISRC pre-check
     against `tidal_seed_isrc` before chain starts
   - `6c`: pass criteria, failure mode table, step-by-step run instructions

3. **Environment additions** — `spotify_access_token`, `tidal_seed_track_id`,
   `tidal_seed_isrc`, `spotify_verified_id` — documented in patch.md

**Files created**:
- `Identity Verification/5c - Spotify ISRC Cross-Check.request.yaml`
- `Validation Run/6a - Resolve TIDAL Album to ISRC.request.yaml`
- `Validation Run/6b - Track by ID (Validation).request.yaml`
- `Validation Run/6c - Run Notes.request.yaml`

**Tests run**: None.

**Pending operator steps before chain can run**:
- Add 4 env variables in Postman desktop (see `environments/tagslut.environment.yaml.patch.md`)
- Resolve `beatport_test_track_id` via `Catalog / Tracks by ISRC` using ISRC from `6a`
- Run Collection Runner: `6a → 6b → 5a → 5b → 5c`
- Pass criteria: no field WARNINGs, `5b` + `5c` both log `CORROBORATED`

**Remaining**: Task 8 — collection-level token expiry guard (single script, low priority).

---

## Session: 2026-03-21 (pass 5) — Postman API Collection + Multi-Provider ID Policy

**Task**: Finalize Beatport API Postman collection; define multi-provider ID policy and confidence tier revision.

**Status**: Completed — commit `6ab432b`, 6 files changed, 276 insertions, 57 deletions.

**What was done**: Collection cleanup (3 stale collections deleted), `base_url` + token
expiry tracking added, ISRC endpoint auth confirmed (Basic not Bearer), Track by ID
field validation, Identity Verification folder with `5a` (Beatport) + `5b` (TIDAL)
cross-check chain. Multi-provider ID policy written (`MULTI_PROVIDER_ID_POLICY.md`),
five-tier confidence model defined (`corroborated` tier added), tiddl config documented
(`TIDDL_CONFIG.md`).

---

## Session: 2026-03-21 (pass 4) — Repo Cleanup, DB Epoch Management, Context Bundle

**Status**: Completed. Epoch renamed, backups pruned, artifacts archived to SAD,
sensitive files deleted, DB symlink added, STAGING_ROOT fixed, context bundle script
written, PROJECT_DIRECTIVES.md created, ROADMAP revised.

---

## Session: 2026-03-21 (pass 3) — Ingestion Provenance Standard

**Status**: Completed. `INGESTION_PROVENANCE.md` written, CORE_MODEL Rules 6–7 added,
ROADMAP §14 added. Four-tier model — superseded by pass 5 five-tier revision.

---

## Session: 2026-03-21 (pass 2) — Ingestion Provenance Memo Correction

**Status**: Completed. All four provenance fields confirmed NOT NULL, no DEFAULT.
Implementation ordering corrected. ~25 test fixtures require updates.

---

## Session: 2026-03-21 (pass 1) — Ingestion Provenance Migration Spec

**Status**: Completed. Five insert surfaces identified. Two migration paths required
(SQLite + Postgres). Six doc/schema inconsistencies documented.

---

## Session: 2026-03-21 — Resume-Refresh Fix Verification

**Status**: Completed. All three root causes verified as already implemented.
`poetry run pytest tests/exec/test_resume_refresh.py -v` — **7/7 PASSED**
Commits: 730d2b1, 2fb2a50, 3f3f37d, bf3df38, 0a98453

---

## Previous Report — 2026-03-14

The v3 core surface is active. DJ pipeline schema migration (0010) applied,
full Lexicon DJ → track_identity metadata backfill completed.

- `lexicon_backfill.py`: 20,517 identities enriched, 29,442 rows in `reconcile_log`
- 11,679 identities unmatched (36% — tracks not in Lexicon)
- Tests: 579 passed, 2 failed, 1 warning (March 8 baseline — stale)
- `track_identity` rows with Lexicon energy: 15,881 / 32,196 (49%)
