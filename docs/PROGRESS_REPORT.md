<!-- Status: Active document. Synced 2026-03-22 after credential consolidation phase 1 and tools/get fix. -->

# Progress Report

Report date: March 22, 2026

## Session: 2026-03-22 (pass 3) — Credential Consolidation Phase 1 + tools/get fix

**Task**: Fix credential precedence, add token-get CLI, migrate harvest scripts,
document credential model. Fix tools/get FORWARD_ARGS zsh bug.

**Status**: Completed — commits `249ac8d` (credential consolidation) + cherry-pick
from `fix/get-forward-args-zsh` branch (tools/get fix). 7 files changed total.

**What was done**:

1. **beatport.py precedence fix** — `_auth_config()` now checks `TokenManager`
   first, env vars as fallback with `logger.warning`. All three credential fields
   affected: bearer token, catalog username, catalog password.

2. **`tagslut auth token-get <provider>`** — new CLI subcommand. Prints only the
   raw access token to stdout (suitable for shell capture). Exits 1 with error
   on stderr when token is missing or expired. Supports `beatport` and `tidal`.

3. **Harvest scripts** — both `beatport_harvest_my_tracks.sh` and
   `beatport_harvest_catalog_track.sh` now use:
   `BEATPORT_ACCESS_TOKEN=$(tagslut auth token-get beatport 2>/dev/null)`
   `source env_exports.sh` removed entirely.

4. **`tests/cli/test_auth_token_get.py`** — 4 new tests: happy path, missing
   token, expired token, unsupported provider. All passing.

5. **`docs/CREDENTIAL_MANAGEMENT.md`** — operator-facing guide documenting
   tokens.json-first model, per-provider setup, token-get usage, precedence
   rule, Postman note, token rotation.

6. **tools/get FORWARD_ARGS fix** — empty array expansion in zsh (`${FORWARD_ARGS[@]}`
   with `set -u`) caused `unbound variable` error. Fixed with safe expansion:
   `${FORWARD_ARGS[@]+"${FORWARD_ARGS[@]}"}`. Verified working:
   `tools/get https://tidal.com/album/497862476/u` — 18 tracks downloaded.

**Tests run**: `tests/metadata/ -k beatport` + `tests/cli/ -k token_get` — ALL PASS.

---

## Session: 2026-03-22 (pass 2) — Migration 0012 Complete

**Status**: Completed — commit `bef5931`, 6 files, 16 tests passing.

Legacy init_db path updated, CHECK constraints added, test fixtures fixed,
`DB_V3_SCHEMA.md` updated with vocabulary tables.

---

## Session: 2026-03-22 (pass 1) — Migration 0012 prompt written

**Status**: Completed. `.github/prompts/migration-0012-provenance.prompt.md` written
and committed. All blocking decisions resolved in the prompt.

---

## Session: 2026-03-21 (pass 8) — TIDAL OAuth Refactor

**Status**: Completed — commit `3a3595c`. Global mutable state removed, monotonic
clock, private naming, docstring restored. No behaviour changes.

---

## Session: 2026-03-21 (pass 7) — Postman Collection-Level Token Guard

**Status**: Completed — commit `14c9e29`. Postman agent track fully complete.

---

## Session: 2026-03-21 (pass 6) — Postman Validation Run + Spotify Chain

**Status**: Completed — commit `37619ae`. `5c` Spotify, Validation Run folder.

---

## Session: 2026-03-21 (pass 5) — Postman API Collection + Multi-Provider ID Policy

**Status**: Completed — commit `6ab432b`. Collection cleanup, ISRC auth, Identity
Verification chain, multi-provider ID policy, five-tier confidence model.

---

## Session: 2026-03-21 (pass 4) — Repo Cleanup, DB Epoch Management, Context Bundle

**Status**: Completed. Epoch renamed, artifacts archived, PROJECT_DIRECTIVES.md,
ROADMAP revised.

---

## Session: 2026-03-21 — Resume-Refresh Fix Verification

**Status**: Completed. 7/7 PASSED. Commits: 730d2b1, 2fb2a50, 3f3f37d, bf3df38.

---

## Previous Report — 2026-03-14

v3 core surface active. DJ pipeline migration (0010), Lexicon backfill complete.
20,517 identities enriched, 11,679 unmatched (36%). Tests: 579 passed, 2 failed.
