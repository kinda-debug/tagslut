# Credential Management Consolidation — Phase 1

<!-- Created: 2026-03-22 -->
<!-- Spec: docs/CREDENTIAL_MANAGEMENT_AUDIT.md + docs/ROADMAP.md §18 -->

Agent instructions: AGENT.md, CLAUDE.md, docs/PROJECT_DIRECTIVES.md

Read first:
  tagslut/metadata/auth.py           — TokenManager (System B, already complete)
  tagslut/metadata/providers/beatport.py  — line ~224, the precedence bug
  tagslut/metadata/beatport_harvest_my_tracks.sh  — sources env_exports.sh
  tagslut/metadata/beatport_harvest_catalog_track.sh  — same
  tagslut/cli/commands/auth.py       — existing auth CLI surface

---

## Context

Two credential systems operate in parallel. System B (TokenManager +
~/.config/tagslut/tokens.json) is the correct approach and is already
fully implemented in auth.py. System A (env_exports.sh) is archived
but still referenced. Phase 1 closes the three concrete gaps that
affect daily operations.

---

## Task 1 — Fix precedence in beatport.py (~line 224)

PROBLEM:
  In `BeatportApiClient._auth_config()`:
    search_bearer_token=os.getenv("BEATPORT_ACCESS_TOKEN") or (token.access_token if token else None)

  Env var wins over TokenManager. A stale env var silently overrides
  a fresh token from tokens.json. No warning is logged.

FIX:
  Reverse the order and add a warning log:

    _env_token = os.getenv("BEATPORT_ACCESS_TOKEN")
    if _env_token:
        logger.warning(
            "Using BEATPORT_ACCESS_TOKEN from environment variable. "
            "Consider moving credentials to tokens.json via 'tagslut auth login beatport'."
        )
    _mgr_token = token.access_token if token else None
    search_bearer_token = _mgr_token or _env_token,

  tokens.json now wins. Env var is fallback with a logged warning.

  Apply the same pattern to catalog_basic_username and
  catalog_basic_password: TokenManager credentials first, env var
  fallback with warning.

VERIFY:
  poetry run pytest tests/metadata/ -v -k "beatport"

Commit: fix(auth): tokens.json takes precedence over env vars in beatport provider

---

## Task 2 — Add `tagslut token-get <provider>` CLI command

PURPOSE:
  Shell scripts cannot call Python TokenManager. This command bridges
  the gap by printing the access token to stdout so scripts can capture it:
    BEATPORT_ACCESS_TOKEN=$(tagslut token-get beatport)

IMPLEMENTATION:
  Add a `token-get` subcommand to the `tagslut auth` CLI group in
  `tagslut/cli/commands/auth.py`.

  Behaviour:
  - Call `TokenManager().ensure_valid_token(provider)`
  - If token is valid: print only the access_token string to stdout, exit 0
  - If token is missing: print error to stderr, exit 1
  - If token is expired and cannot be refreshed: print error to stderr, exit 1
  - No other output — stdout must contain only the token string (for shell capture)

  Supported providers: beatport, tidal
  Usage: `tagslut auth token-get beatport`

  Example:
    $ tagslut auth token-get beatport
    eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...
    $ echo $?
    0

    $ tagslut auth token-get beatport  # when expired/missing
    Error: No valid Beatport token. Run 'tagslut auth login beatport'.
    $ echo $?
    1

VERIFY:
  poetry run pytest tests/cli/ -v -k "token_get or token-get"
  # If no test exists, write one:
  # - Mock TokenManager, assert stdout contains only access_token on success
  # - Assert exit code 1 when token missing

Commit: feat(auth): add token-get CLI command for shell script credential access

---

## Task 3 — Update harvest scripts to use token-get

FILES:
  tagslut/metadata/beatport_harvest_my_tracks.sh
  tagslut/metadata/beatport_harvest_catalog_track.sh

PROBLEM:
  Both scripts source env_exports.sh (archived, legacy System A):
    source "${PROJECT_ROOT}/env_exports.sh"

FIX:
  Replace the `source env_exports.sh` block and the
  `BEATPORT_ACCESS_TOKEN` check with:

    # Get Beatport token from TokenManager (System B)
    if ! BEATPORT_ACCESS_TOKEN="$(tagslut auth token-get beatport 2>/dev/null)"; then
        echo "ERROR: No valid Beatport token." >&2
        echo "Run: tagslut auth login beatport" >&2
        exit 1
    fi
    export BEATPORT_ACCESS_TOKEN

  Remove the env_exports.sh source line entirely.
  Remove any comment referencing env_exports.sh.

  Do NOT change any other part of the scripts — only the credential
  acquisition block.

VERIFY:
  # Dry-run test — confirm the scripts parse without error:
  bash -n tagslut/metadata/beatport_harvest_my_tracks.sh
  bash -n tagslut/metadata/beatport_harvest_catalog_track.sh

Commit: fix(auth): replace env_exports.sh with token-get in harvest scripts

---

## Task 4 — Write docs/CREDENTIAL_MANAGEMENT.md

Write a concise operator-facing guide. Cover:

1. Where credentials live: ~/.config/tagslut/tokens.json
2. How to initialize: `tagslut auth init`
3. Per-provider setup:
   - TIDAL: `tagslut auth login tidal` (device flow, auto-refresh)
   - Beatport: paste JWT from dj.beatport.com DevTools, 1-hour expiry,
     no auto-refresh, re-paste when expired
4. How to check status: `tagslut auth status`
5. Precedence rule: tokens.json wins. Env vars are fallback with a
   logged warning. Never set BEATPORT_ACCESS_TOKEN in shell permanently.
6. Postman: Postman environment vars are for API testing only.
   They are not a source of truth. Copy token from tokens.json manually
   when running Postman tests.
7. Rotating a Beatport token: paste new token via `tagslut auth login beatport`
   or edit tokens.json directly.

Keep it under 80 lines. No duplication of auth.py docstrings.

Commit: docs(auth): add credential management guide

---

## Exit criteria

1. poetry run pytest tests/metadata/ -v -k "beatport" — ALL PASS
2. poetry run pytest tests/cli/ -v -k "token_get or token-get" — ALL PASS
3. bash -n on both harvest scripts — no errors
4. docs/CREDENTIAL_MANAGEMENT.md exists and covers all four sections
5. No references to env_exports.sh remain in active (non-archived) code

## Escalate to Claude Code if

- The `tagslut auth` CLI group structure is unclear or token-get
  conflicts with an existing subcommand
- beatport.py precedence fix causes a test to fail for unexpected reasons
- env_exports.sh is referenced in any file outside archive/ and metadata/
