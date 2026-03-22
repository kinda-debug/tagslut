<!-- Status: Active document. Synced 2026-03-22 after dual-write fix and intake pipeline hardening. -->

# Progress Report

Report date: March 22, 2026

## Session: 2026-03-22 (pass 4) — Intake pipeline v3 fix + `--backfill` mode

**Status**: Completed — commits `ed6f47c`, `6acc6db`, `d70ed93`, pending commit.

**Root cause identified and fixed**: `dual_write` config flag was `false` by default
(no `~/.config/tagslut/config.toml` existed). Every intake run wrote to the legacy
`files` table only. The v3 `asset_file` + `track_identity` tables were never populated,
making the entire DJ pipeline invisible to new files.

**What was done**:

1. **`~/.config/tagslut/config.toml` created** with `dual_write = true`. This is the
   single fix that unblocks all v3/DJ functionality. Documented in `.env.example`.

2. **`tools/get --backfill` mode added** (`ed6f47c`) — new mode that downloads only
   missing tracks from a provider URL, then registers + enriches (DJ tags always
   included) + promotes. Existing files in the batch root are not re-downloaded.
   Usage: `tools/get --backfill https://tidal.com/album/XXXXX/u`

3. **`index register` default changed to `--no-prompt`** (`6acc6db`) — was blocking
   on every similar-file match during batch processing. Now auto-skips silently.
   Pass `--prompt` explicitly for interactive review.

4. **`post_move_enrich_art.py` patched** (`d70ed93` + this session):
   - Added `dual_write_registered_file()` call per promoted FLAC after intake,
     populating `asset_file` + `track_identity` automatically going forward.
   - Added `compute_identity_statuses()` + `compute_preferred_assets()` refresh
     at end of every background enrich run, keeping DJ candidate view current.

5. **One-time DB backfill**: 174 files already in MASTER_LIBRARY were backfilled
   into v3 schema manually (Python script). Canonical fields synced from `files`
   → `track_identity`. `identity_status` and `preferred_asset` populated.
   Result: `v_dj_pool_candidates_active_v3` = 170 rows, DJ pipeline functional.

6. **Orphan cleanup**: 24,603 `files` rows written by a premature `index register`
   run (before dual_write was enabled) were deleted. DB is clean.

**DB state after this session**:
- `files`: 174 rows (legacy, enriched)
- `asset_file`: 174 rows (v3)
- `track_identity`: 170 rows (all with ISRC, canonical fields populated)
- `identity_status`: 170 active
- `preferred_asset`: 170
- `v_dj_pool_candidates_active_v3`: 170 ✅

---

## Session: 2026-03-22 (pass 3) — Credential Consolidation Phase 1 + tools/get fix

**Status**: Completed — commits `249ac8d` + cherry-pick from `fix/get-forward-args-zsh`.

**What was done**: beatport.py precedence fix, `tagslut auth token-get` CLI,
harvest scripts migrated, `CREDENTIAL_MANAGEMENT.md` written, FORWARD_ARGS zsh fix.

---

## Session: 2026-03-22 (pass 2) — Migration 0012 Complete

**Status**: Completed — commit `bef5931`, 6 files, 16 tests passing.

---

## Session: 2026-03-22 (pass 1) — Migration 0012 prompt written

**Status**: Completed.

---

## Session: 2026-03-21 (pass 8) — TIDAL OAuth Refactor

**Status**: Completed — commit `3a3595c`.

---

## Session: 2026-03-21 (pass 7) — Postman Collection-Level Token Guard

**Status**: Completed — commit `14c9e29`.

---

## Session: 2026-03-21 (pass 6) — Postman Validation Run + Spotify Chain

**Status**: Completed — commit `37619ae`.

---

## Session: 2026-03-21 (pass 5) — Postman API Collection + Multi-Provider ID Policy

**Status**: Completed — commit `6ab432b`.

---

## Session: 2026-03-21 (pass 4) — Repo Cleanup, DB Epoch Management

**Status**: Completed.

---

## Session: 2026-03-21 — Resume-Refresh Fix Verification

**Status**: Completed. 7/7 PASSED. Commits: 730d2b1, 2fb2a50, 3f3f37d, bf3df38.

---

## Previous Report — 2026-03-14

v3 core surface active. DJ pipeline migration (0010), Lexicon backfill complete.
20,517 identities enriched, 11,679 unmatched (36%). Tests: 579 passed, 2 failed.
