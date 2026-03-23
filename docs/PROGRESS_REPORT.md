<!-- Status: Active document. Synced 2026-03-23 after lexicon pipeline + master scan session. -->

# Progress Report

Report date: March 23, 2026

## Session: 2026-03-23 — Lexicon pipeline, master scan, schema fixes, symlink removal

**Status**: Completed — commits pending (schema fix + roadmap update).

**What was done**:

1. **Symlink trap removed.** `/Users/georgeskhawam/Projects/tagslut_db/music_v3.db` was a
   symlink pointing to the LEGACY (Picard-contaminated) DB. Removed permanently. The Codex
   lexicon-reconcile session had routed all execute commands through this symlink. All
   subsequent commands used the explicit FRESH DB path.

2. **Codex schema bug caught and patched.** The new `mp3 reconcile-scan` and `master scan`
   commands invented two non-existent columns (`source`, `status`) in their `track_identity`
   stub inserts. Patched in `tagslut/exec/mp3_build.py` and `tagslut/exec/master_scan.py`
   to use the correct provenance columns. Verified: reconcile-scan re-run → 0 errors.

3. **Full pipeline executed against FRESH DB** (run_id `a655f8d4`):
   - `mp3 scan`: 1,819 files → `data/mp3_scan_20260323.csv`
   - `mp3 reconcile-scan --execute`: t2=1, stubs=1,816, errors=0
   - `lexicon import --execute`: 9 matched, 19 fields written, 0 errors
   - `lexicon import-playlists --execute`: 0 playlists (allowlist filtered all — needs investigation)
   - `master scan --execute`: inserted=25,324, matched=18, stubs=25,306, errors=0

4. **FRESH DB state after session**:
   `track_identity`=188 (all `provider_api/high`, no stubs) · `asset_file`=25,534 ·
   `mp3_asset`=1 · `dj_playlist`=0 · `reconcile_log`=27,163 · `identity_status`=188 active

5. **Roadmap updated**: §5 marked complete (pre-existing); §3.5 reclassified as
   pipeline-state-dependent.

**Open items from this session**:
- Commit: `chore(schema): fix stub inserts in mp3_build and master_scan`
- Commit: `docs(roadmap): mark §5 complete, reclassify §3.5`
- Investigate `lexicon import-playlists` 0 result — check allowlist vs actual Lexicon playlist names
- Run `tagslut mp3 missing-masters --db FRESH_PATH` (read-only)
- Close the Claude Code session that spawned `master scan --execute` without confirmation

---

## Session: 2026-03-22 (pass 6) — §3.4 XML validation gate doc audit + roadmap close

**Status**: Completed — no new code commits; roadmap updated.

**What was done**:

1. **Documentation completeness audit for §3.4** (XML validation gate). Verified all five active
   operator docs contain the gate behavior:
   - `docs/DJ_PIPELINE.md` — "Pre-emit gate:" bullet block and `dj_validation_state` in Outputs
   - `docs/DJ_WORKFLOW.md` — `state_hash` paragraph, gate refusal bullets, `--skip-validation` warning
   - `README.md` — Stage 4 comments (emergency `--skip-validation` note)
   - `docs/OPERATIONS.md` — rerun note + prose gate explanation
   - `CHANGELOG.md` — `dj_validation_state` entry and Changed entry

2. **Secondary docs deferred intentionally.** `docs/SCRIPT_SURFACE.md` and `docs/ARCHITECTURE.md`
   contain references to `dj validate` but are secondary references, not operator workflow docs.
   No change needed to unblock further work.

3. **Roadmap §3.4 closed.** Marked COMPLETE. Both §3.3 (FFmpeg validation) and §3.4 (XML
   validation gate) are fully resolved. DJ pipeline hardening (§3) is complete pending §3.5
   (DJ admission backfill, which is a no-op against an empty DB).

---

## Session: 2026-03-22 (pass 5) — DJ FFmpeg validation + stop-point capture

**Status**: Completed and paused here — commits `de59b4f`, `d234572`, `2d48601`, `ea266a3`.

**What was done**:

1. **FFmpeg output validation landed** (`de59b4f`) in the DJ transcode path.
   Successful ffmpeg exit is no longer accepted on its own; the output MP3 is now
   checked for existence, minimum size, mutagen readability, and duration > 1 second.

2. **Focused test coverage added** for the FFmpeg validation path in
   `tests/exec/test_mp3_build_ffmpeg_errors.py`, covering missing ffmpeg,
   non-zero exit, missing output, undersized output, unreadable MP3, valid output,
   and DJ pool wizard failure surfacing.

3. **Operator docs updated** (`d234572`, `2d48601`) so the Stage 2 transcode safety
   contract and the Stage 4 XML validation-gate behavior are reflected in active docs.

4. **Follow-up cleanup completed** (`ea266a3`) by removing a duplicate
   `_run_ffmpeg_transcode()` definition from `tagslut/exec/transcoder.py`.
   Verification after cleanup:
   `poetry run pytest tests/exec/test_transcoder.py tests/exec/test_mp3_build_ffmpeg_errors.py -v --tb=short`
   Result: 14 passed.

**Important stop-point note**:
A broader `dj_validation_state` / XML preflight validation gate feature was included in
this same work window. It is beyond the original FFmpeg-only prompt and should be reviewed
as a separate DJ hardening item before further changes continue.

---

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
