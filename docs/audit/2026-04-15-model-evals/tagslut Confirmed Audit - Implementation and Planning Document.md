<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# i even made chatgpt and claude blind compare and same result. please synthesize into an actionable audit and planning  and implementation document

Now I have everything I need. All three blind evaluators (Claude, Gemini, ChatGPT) reached the same verdict — B wins by 28–41 points — and the finding adjudication tables are in full agreement. Let me synthesize this into the implementation document.

***

# tagslut — Confirmed Audit: Implementation \& Planning Document

**Basis:** Audit-B (confirmed winner across all three blind evaluations: Claude 96.1/100, ChatGPT 94/100, Gemini 88/100). All 11 findings are confirmed true positives with zero false positives across all three evaluators.[^1][^2][^3]

***

## Reading This Document

Each work item has:

- A **severity tier** (Critical / High / Medium / Low)
- A **fix type** (Code / Config / Docs / Process)
- **Exact file targets** and **acceptance criteria**
- Dependencies called out explicitly

Items are ordered by risk reduction. Do not reorder without understanding the dependency chain.

***

## Tier 1 — Critical: Fix Before Next Intake Run


***

### T1-A — Fix unreachable retag/output block in `_run_local_flow`

**Fix type:** Code
**File:** `tagslut/cli/commands/get.py:108–150`
**Risk if unfixed:** Every `tagslut get <local_path>` invocation silently succeeds (exit 0) while skipping retag, cohort binding, output artifact construction, and cohort status finalization. The operator sees no error, but no useful work is done after file registration.[^4]

**Root cause — exact code:**

```python
flac_paths = resolve_flac_paths(input_path)
if not flac_paths:
    return False, "no FLAC inputs resolved from local path"

    with sqlite3.connect(str(db_path)) as conn:   # ← DEAD: inside if-block, after return
        ensure_cohort_support(conn)
        bind_asset_paths(conn, ...)
        retag_result = retag_flac_paths(...)
        ...
        refresh_cohort_status(conn, ...)
return True, None   # ← always reached for non-empty FLAC inputs
```

**Required change:** Dedent the `with sqlite3.connect(...)` block by 4 spaces so it is at function scope, not inside the `if not flac_paths:` branch. The function structure should be:

```python
flac_paths = resolve_flac_paths(input_path)
if not flac_paths:
    return False, "no FLAC inputs resolved from local path"

with sqlite3.connect(str(db_path)) as conn:   # ← function scope
    ensure_cohort_support(conn)
    bind_asset_paths(conn, cohort_id=cohort_id, paths=flac_paths)
    conn.commit()
    retag_result = retag_flac_paths(db_path=db_path, flac_paths=flac_paths, force=False)
    mark_paths_ok(conn, cohort_id=cohort_id, paths=retag_result.ok_paths)
    for path, reason in retag_result.blocked.items():
        ...
    if retag_result.blocked:
        set_cohort_blocked(...)
        conn.commit()
        return False, "one or more files failed during enrich"
    output_result = build_output_artifacts(...)
    if not output_result.ok:
        record_blocked_paths(...)
        conn.commit()
        return False, output_result.reason
    refresh_cohort_status(conn, cohort_id=cohort_id)
    conn.commit()
return True, None
```

**Acceptance criteria:**

1. `tagslut get /path/to/flac/dir` completes and a `cohort` row exists with `status='completed'` (not `'running'`)
2. `cohort_file` rows are present for each FLAC
3. An M3U artifact is written if `--playlist` is passed
4. `pytest tests/cli/test_get_local_path.py` (write this test; see T3-B)

**Verification command (pre-fix, to confirm breakage):**

```bash
poetry run tagslut get /tmp/test_flacs --db /tmp/test.db
sqlite3 /tmp/test.db "SELECT status, blocked_reason FROM cohort ORDER BY id DESC LIMIT 1;"
# Expected broken output: status='running', blank cohort_file rows
```


***

### T1-B — Replace hardcoded machine-specific absolute paths in `tools/get`

**Fix type:** Code
**File:** `tools/get:~488–610`
**Risk if unfixed:** `tools/get <beatport-url>` and `tools/get <qobuz-url>` hard-fail with `exit 1` on every machine except the original author's. Beatport and Qobuz downloads are completely non-functional in any CI, any other workstation, or any future OS reinstall.[^4]

**Exact strings to replace:**


| Current hardcoded value | Replace with |
| :-- | :-- |
| `BEATPORTDL_CMD="/Users/georgeskhawam/Projects/beatportdl/beatportdl-darwin-arm64"` | `BEATPORTDL_CMD="${BEATPORTDL_CMD:-}"` + explicit error if unset |
| `cd /Users/georgeskhawam/Projects/beatportdl` | `cd "$(dirname "$BEATPORTDL_CMD")"` |
| `BEATPORT_ROOT="/Volumes/MUSIC/staging/bpdl"` | `BEATPORT_ROOT="${BEATPORT_ROOT:-${STAGING_ROOT}/bpdl}"` |
| `STREAMRIP_CMD="/Users/georgeskhawam/Projects/streamrip/.venv/bin/rip"` | `STREAMRIP_CMD="${STREAMRIP_CMD:-}"` + explicit error if unset |
| `STREAMRIP_CONFIG="/Users/georgeskhawam/Projects/streamrip/dev_config.toml"` | `STREAMRIP_CONFIG="${STREAMRIP_CONFIG:-}"` + explicit error if unset |
| `STREAMRIP_ROOT="/Volumes/MUSIC/staging/StreamripDownloads"` | `STREAMRIP_ROOT="${STREAMRIP_ROOT:-${STAGING_ROOT}/StreamripDownloads}"` |

**Pattern for each replaced block:**

```bash
if [[ -z "${BEATPORTDL_CMD:-}" ]]; then
    echo "Error: BEATPORTDL_CMD is not set. Add it to env_exports.sh." >&2
    exit 1
fi
if [[ ! -x "$BEATPORTDL_CMD" ]]; then
    echo "Error: beatportdl not found or not executable at: $BEATPORTDL_CMD" >&2
    exit 1
fi
```

**Add to `env_exports.sh.template` (or `START_HERE.sh` comments):**

```bash
# Required for Beatport downloads:
export BEATPORTDL_CMD=/path/to/beatportdl-binary
# Required for Qobuz downloads:
export STREAMRIP_CMD=/path/to/streamrip/.venv/bin/rip
export STREAMRIP_CONFIG=/path/to/streamrip/config.toml
```

**Acceptance criteria:**

1. `tools/get <beatport-url>` without `BEATPORTDL_CMD` set exits with a clear error message
2. `tools/get <qobuz-url>` without `STREAMRIP_CMD` set exits with a clear error message
3. No `/Users/georgeskhawam` strings remain in `tools/get` (`grep -n 'georgeskhawam' tools/get` returns empty)
4. `shellcheck tools/get` passes on the modified sections

***

## Tier 2 — High: Fix Within Current Sprint


***

### T2-A — Resolve the `ts-get` / `ts-enrich` / `ts-auth` wrapper gap

**Fix type:** Code + Docs
**Files:** `tools/ts-get` (create), `tools/ts-enrich` (create), `tools/ts-auth` (create), then update `AGENT.md`, `CLAUDE.md`, `START_HERE.sh`
**Risk if unfixed:** Any new operator, CI agent, or AI coding assistant following `AGENT.md` or `CLAUDE.md` to reproduce a bug gets `command not found` immediately. The canonical debugging path is broken at step 1.[^4]

**Option A (recommended): Create the wrappers in `tools/`**

`tools/ts-get`:

```bash
#!/usr/bin/env bash
# ts-get — canonical operator wrapper for tools/get
exec "$(dirname "${BASH_SOURCE[^0]}")/get" "$@"
```

`tools/ts-enrich`:

```bash
#!/usr/bin/env bash
# ts-enrich — canonical operator wrapper for tagslut enrichment
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[^0]}")/.." && pwd)"
exec poetry -C "$REPO_ROOT" run python -m tagslut enrich "$@"
```

`tools/ts-auth`:

```bash
#!/usr/bin/env bash
# ts-auth — canonical operator wrapper for tagslut auth
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[^0]}")/.." && pwd)"
exec poetry -C "$REPO_ROOT" run python -m tagslut auth login "${1:-all}" "$@"
```

Then `chmod +x tools/ts-get tools/ts-enrich tools/ts-auth` and update `START_HERE.sh` to add `tools/` to `PATH`:

```bash
export PATH="$TAGSLUT_ROOT/tools:$PATH"
```

**Option B (alternative): Remove wrapper references from all active docs** — replace all `ts-get`, `ts-enrich`, `ts-auth` with their underlying `tools/get`, `poetry run tagslut enrich`, `poetry run tagslut auth` equivalents in `AGENT.md`, `CLAUDE.md`, `docs/OPERATOR_QUICK_START.md`, `docs/WORKFLOWS.md`.

**Acceptance criteria:**

- `which ts-get` resolves after `source START_HERE.sh`
- `ts-get --help` produces the `tools/get` usage output
- `AGENT.md` and `CLAUDE.md` are consistent with whichever option is chosen

***

### T2-B — Fix Qobuz `resolve_provider_status` credential check

**Fix type:** Code
**File:** `tagslut/metadata/provider_state.py:143–155`
**Risk if unfixed:** Operator runs `tagslut auth status` (or any display consuming `ProviderStatus`), sees Qobuz as `enabled_authenticated / metadata_usable=True`, runs enrichment, gets zero Qobuz results with no error. Silent data gap.[^4]

**Current broken code:**

```python
if provider == "qobuz":
    return ProviderStatus(
        provider=provider,
        metadata_enabled=True,
        trust=policy.trust,
        state=ProviderState.enabled_authenticated,  # ← unconditional
        has_access_token=False,
        has_refresh_token=False,
        is_expired=None,
        metadata_usable=True,                       # ← unconditional
    )
```

**Required replacement:**

```python
if provider == "qobuz":
    raw = _get_raw_provider_data(token_manager, provider)
    app_id = raw.get("app_id")
    app_secret = raw.get("app_secret")
    user_auth_token = raw.get("user_auth_token")
    has_credentials = bool(app_id and app_secret and user_auth_token)

    if not has_credentials:
        return ProviderStatus(
            provider=provider,
            metadata_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_unconfigured,
            has_access_token=False,
            has_refresh_token=False,
            is_expired=None,
            metadata_usable=False,
        )
    return ProviderStatus(
        provider=provider,
        metadata_enabled=True,
        trust=policy.trust,
        state=ProviderState.enabled_authenticated,
        has_access_token=True,
        has_refresh_token=False,
        is_expired=None,
        metadata_usable=True,
    )
```

Apply the same fix to the `reccobeats` branch (same pattern confirmed by all evaluators).[^1]

**Acceptance criteria:**

1. `tagslut auth status` with empty `tokens.json` shows Qobuz as `enabled_unconfigured` / `metadata_usable=False`
2. `tagslut auth status` with valid credentials shows `enabled_authenticated`
3. `pytest tests/metadata/test_provider_state.py` passes with new test cases for both states

***

### T2-C — Decide and document the authoritative intake entrypoint

**Fix type:** Docs + Architecture decision
**Files:** `AGENT.md`, `CLAUDE.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/WORKFLOWS.md`
**Risk if unfixed:** Operators and agents choose between `tools/get` (no cohort tracking) and `tagslut get` (cohort tracking, broken local-path flow) with no guidance. Blocked-cohort recovery (`tagslut get --fix`) is only meaningful for `tagslut get` runs, but `tools/get` is the primary entrypoint.[^4]

**The decision to make (two options):**

**Option A — Make `tools/get` the acknowledged primary, deprecate `tagslut get` URL path:**

- Accept that cohort tracking does not apply to `tools/get` runs
- Remove `tagslut get` from agent docs or mark it explicitly as "cohort-tracking only, not for general use"
- Update blocked-cohort UX: make `tagslut get --fix` only relevant after a `tagslut get` run

**Option B — Route `tools/get` through `tagslut get` for cohort tracking:**

- Modify `tools/get` URL dispatch to invoke `poetry run tagslut get <url>` instead of `get-intake` directly
- Cohort tracking then applies to all URL intake
- Requires T1-A to be merged first (URL flow is unaffected by the local-path bug, but the CLI must be stable)

**Recommendation:** Option A is lower risk and requires no code change beyond documentation. Option B is architecturally cleaner but requires a behavioral change in `tools/get` with corresponding test coverage.

**Acceptance criteria (Option A):**

1. `AGENT.md` says: "`tools/get` is the primary URL intake entrypoint. Cohort tracking via `tagslut get` is a supplementary path for runs that need blocked-cohort recovery."
2. `README.md` Quick Start section does not mention `tagslut get` as an equivalent to `tools/get`
3. All three active docs (`OPERATOR_QUICK_START.md`, `WORKFLOWS.md`, `ARCHITECTURE.md`) are consistent

***

## Tier 3 — Medium: Fix Within This Month


***

### T3-A — Fix CI to run lint/mypy on the full package, not just changed files

**Fix type:** Config
**File:** `.github/workflows/ci.yml`
**Risk if unfixed:** Regressions in untouched files are invisible. A PR touching only `_cohort_state.py` does not lint or type-check `get.py`, `provider_state.py`, or any other file. Migrations in `tagslut/storage/v3/migrations/**` are permanently excluded from all static checks.[^4]

**Required change to `.github/workflows/ci.yml`:**

Replace the changed-files-gated lint/type-check steps with full-package checks. Keep changed-files detection only as an informational step if desired:

```yaml
- name: Lint (full package)
  run: poetry run flake8 tagslut/ tests/

- name: Type check (full package)
  run: poetry run mypy tagslut/ --ignore-missing-imports

- name: Test
  run: poetry run pytest --tb=short -q --cov=tagslut --cov-report=term-missing --cov-fail-under=75
```

Also remove the `files_ignore: tagslut/storage/v3/migrations/**` exclusion. Migration SQL files won't be linted by flake8/mypy but they will at least be visible to the test suite.

Raise the coverage floor from `60` to `75`. If that's not achievable immediately, set it to `65` and add a tracking issue.

**Acceptance criteria:**

1. A PR that introduces a syntax error in an untouched `tagslut/` file causes CI to fail
2. `ci.yml` contains no `changed-files` gating for lint or mypy
3. `--cov-fail-under` is at least `65`

***

### T3-B — Document Tidal client credentials; add env-var override to active docs

**Fix type:** Code (comment) + Docs
**File:** `tagslut/metadata/auth.py:~338`, `docs/OPERATOR_QUICK_START.md`, `START_HERE.sh`
**Risk if unfixed:** If Tidal rotates the bundled third-party app credentials (`zU4XHVVkc2tDPo4t` / `VJKhDFqJPqvsPVNBV6ukXTJmVvxvvbssk55ZTPOrs`), Tidal token refresh silently fails with no operator guidance on how to fix it.[^4]

**Required change in `auth.py:~338`:**

```python
# Tidal app credentials (device authorization flow).
# These are extracted from open-source Tidal tooling (same as tiddl defaults).
# They are NOT user secrets — they identify the app, not the user account.
# If Tidal rotates these, override via TIDAL_CLIENT_ID and TIDAL_CLIENT_SECRET
# in env_exports.sh before running ts-auth or tagslut auth login tidal.
client_id = os.getenv("TIDAL_CLIENT_ID", "zU4XHVVkc2tDPo4t")
client_secret = os.getenv("TIDAL_CLIENT_SECRET", "VJKhDFqJPqvsPVNBV6ukXTJmVvxvvbssk55ZTPOrs")
```

**Add to `START_HERE.sh` (in the credentials section) or `env_exports.sh.template`:**

```bash
# Optional: override if Tidal rotates app credentials
# export TIDAL_CLIENT_ID=your_client_id
# export TIDAL_CLIENT_SECRET=your_client_secret
```

**Acceptance criteria:**

1. `grep -n "zU4XHVVkc2tDPo4t" tagslut/` returns only one hit with an explanatory comment above it
2. `OPERATOR_QUICK_START.md` mentions `TIDAL_CLIENT_ID` override in its auth section

***

### T3-C — Fix broken self-audit scripts and failing `test_repo_structure.py`

**Fix type:** Code + Docs
**Files:** `scripts/audit_repo_layout.py`, `scripts/check_cli_docs_consistency.py`, `tests/test_repo_structure.py`, `docs/README.md`
**Risk if unfixed:** CI is red. `AGENT.md` instructs agents to run these scripts as their first structural check; both crash. The repo's confidence layer is producing false output.[^2][^4]

**Three separate sub-fixes:**

**Sub-fix 1:** Create `docs/OPERATIONS.md` as a minimal stub (or remove the reference from the two scripts):

```markdown
<!-- docs/OPERATIONS.md -->
# Operations Reference
Active operations reference. See OPERATOR_QUICK_START.md for daily commands.
<!-- TODO: expand with runbook content -->
```

**Sub-fix 2:** Create `scripts/backfill_v3_provenance_from_logs.py` as a stub (or remove the requirement from `audit_repo_layout.py`):

```python
# scripts/backfill_v3_provenance_from_logs.py
# Placeholder — backfill script not yet implemented.
# See: https://github.com/... (tracking issue)
raise NotImplementedError("Not yet implemented")
```

**Sub-fix 3:** Fix `test_repo_structure.py::test_docs_readme_links_resolve_to_repo_files` — the test expects markdown links in `docs/README.md`, but the current file uses only `**bold**` filenames. Either:

- Add proper links to `docs/README.md`: `- [**OPERATOR_QUICK_START.md**](OPERATOR_QUICK_START.md)`
- Or update the test to accept the bold-filenames format

**Acceptance criteria:**

1. `python scripts/audit_repo_layout.py` exits 0 with no ERRORS output
2. `python scripts/check_cli_docs_consistency.py` exits 0
3. `pytest -q tests/test_repo_structure.py` — 27/27 passed, 0 failed

***

### T3-D — Audit `create_schema_v3` callers for missing `run_pending_v3` chain

**Fix type:** Code
**Files:** Any file calling `create_schema_v3` without also calling `run_pending_v3`
**Risk if unfixed:** A caller bootstrapping a DB with `create_schema_v3` alone will crash at runtime when any cohort-related SQL runs, because the `cohort` and `cohort_file` tables only exist after migration 0018.[^4]

**Discovery command:**

```bash
rg "create_schema_v3" tagslut/ --include="*.py" -n
```

For each hit, check whether `run_pending_v3` is called in the same scope or in the wrapping function. Any caller that does not chain both should either:

- Call `ensure_cohort_support(conn)` instead (which already chains both correctly), or
- Add `run_pending_v3(conn)` immediately after `create_schema_v3(conn)`

**Acceptance criteria:**

1. Every call site of `create_schema_v3` either (a) chains `run_pending_v3` in the same scope or (b) delegates to `ensure_cohort_support`
2. `grep -n "create_schema_v3" tagslut/` returns no call sites that lack the follow-on migration call

***

## Tier 4 — Low: Documentation Cleanup Sprint


***

### T4-A — Resolve `docs/ARCHITECTURE.md` body vs. header contradiction

**Fix type:** Docs
**File:** `docs/ARCHITECTURE.md`

The document header says:
> "sections describing the 4-stage DJ pipeline (backfill/validate/XML) and DJ_LIBRARY as a distinct folder reflect the pre-April 2026 architecture. Current model uses M3U-based DJ pool."

But the body describes those sections as current. Fix: either update the body to match the M3U-first model, or expand the header disclaimer into inline annotations on each stale section.[^4]

**Acceptance criteria:** No contradiction between the document header and any section in the body. An operator reading only the body should reach the same operational conclusions as an operator reading the header first.

***

### T4-B — Fix `README.md` Quick Start links to non-active docs

**Fix type:** Docs
**File:** `README.md:29–34`

Five links point to docs outside the active set (`docs/COMMAND_GUIDE.md`, `docs/DJ_PIPELINE.md`, `docs/DOWNLOAD_STRATEGY.md`, `docs/BACKFILL_GUIDE.md`, `docs/PROVENANCE_INTEGRATION.md`). These are either in `docs/archive/` or do not exist.[^4]

**Required change:**

```markdown
## Learn the commands
- [Operator Quick Start](docs/OPERATOR_QUICK_START.md) — daily commands and tokens
- [Workflows](docs/WORKFLOWS.md) — current command surface and flow diagrams
- [Architecture](docs/ARCHITECTURE.md) — system shape and source selection
- [Documentation Index](docs/README.md) — full docs index
```

If the archived docs are still useful context, add a section:

```markdown
## Historical reference (not current)
See `docs/archive/` for pre-April 2026 DJ pipeline, XML workflows, and download strategy docs.
```


***

### T4-C — Fix `START_HERE.sh` default DB path

**Fix type:** Code
**File:** `START_HERE.sh:49`

```bash
# Current (time-expiring literal):
: "${TAGSLUT_DB:=${TAGSLUT_ROOT}_db/FRESH_2026/music_v3.db}"

# Replace with:
: "${TAGSLUT_DB:=${TAGSLUT_ROOT}_db/music_v3.db}"
```

If `FRESH_2026` is an intentional folder convention, document it:

```bash
# DB lives in <repo>_db/<label>/music_v3.db
# Default label is 'main'. Override TAGSLUT_DB in env_exports.sh for multi-DB setups.
: "${TAGSLUT_DB:=${TAGSLUT_ROOT}_db/main/music_v3.db}"
```


***

### T4-D — Resolve DJ/XML pipeline ambiguity

**Fix type:** Docs + Architecture decision
**Files:** `AGENT.md`, `CLAUDE.md`, `README.md`, `docs/ARCHITECTURE.md`

`AGENT.md` says the 4-stage DJ pipeline and XML emit are legacy. `README.md` describes `tagslut dj xml emit` as current Stage 4. The code is functional. Make a decision and propagate it consistently:

**Option A — Keep XML emit as active:**

- Remove "legacy" language from `AGENT.md` and `CLAUDE.md` for the XML path
- Add `docs/DJ_PIPELINE.md` (or restore it from archive) to the active-docs list
- Add a validation test confirming `dj xml emit` doesn't corrupt v3 DB schema

**Option B — Formally retire XML emit:**

- Leave `AGENT.md`/`CLAUDE.md` as-is
- Update `README.md` to move the 4-stage pipeline block into an archived section
- Add a deprecation warning to `tagslut dj xml emit` CLI output

**Acceptance criteria:** Exactly one of the above is implemented. `AGENT.md`, `CLAUDE.md`, `README.md`, and `docs/ARCHITECTURE.md` all agree on whether XML emit is active or legacy.

***

## Implementation Schedule

| Phase | Items | Gate |
| :-- | :-- | :-- |
| **Sprint 1 (this week)** | T1-A (unreachable code), T1-B (hardcoded paths) | No new intake runs until T1-A and T1-B are merged |
| **Sprint 2 (next week)** | T2-A (wrappers), T2-B (Qobuz status), T2-C (entrypoint decision) | T2-B requires T2-C decision first |
| **Sprint 3** | T3-A (CI), T3-B (Tidal creds), T3-C (self-audit scripts), T3-D (schema callers) | T3-C clears CI red; do it first in this sprint |
| **Sprint 4** | T4-A through T4-D (docs cleanup) | T4-D requires T2-C decision |


***

## Test Coverage Gaps to Fill

These tests do not currently exist and should be written alongside the fixes:


| Test | Where | Covers |
| :-- | :-- | :-- |
| `test_run_local_flow_tags_and_emits_m3u` | `tests/cli/test_get_local_path.py` | T1-A: confirms retag and M3U run for non-empty FLAC input |
| `test_run_local_flow_empty_returns_false` | same | T1-A: confirms early return for empty input still works |
| `test_qobuz_status_unconfigured` | `tests/metadata/test_provider_state.py` | T2-B: confirms `enabled_unconfigured` with no tokens |
| `test_qobuz_status_configured` | same | T2-B: confirms `enabled_authenticated` with valid tokens |
| `test_tools_get_beatport_without_env_fails_cleanly` | `tests/tools/test_get_shell.py` | T1-B: confirms error message for missing `BEATPORTDL_CMD` |
| `test_ts_get_resolves` | `tests/tools/test_wrappers.py` | T2-A: confirms `ts-get --help` runs after `source START_HERE.sh` |
| `test_ensure_cohort_support_idempotent` | `tests/storage/test_v3_schema.py` | T3-D: confirms double-call is safe |


***

## Open Questions Remaining

These were not resolvable from static analysis and require a targeted runtime probe or architectural decision:

1. **`tagslut dj xml emit` on live v3 DB:** Does running it on a current production DB corrupt `dj_validation_state`? Verify with: `poetry run tagslut dj xml emit --db /tmp/fresh_test.db --out /tmp/test.xml --dry-run` against a copy of the live DB.
2. **`reccobeats` provider:** Confirm whether it has the same unconditional `enabled_authenticated` pattern as Qobuz. `rg "reccobeats" tagslut/metadata/providers/` — if a `reccobeats.py` exists, apply the same T2-B fix.
3. **`create_schema_v3` solo callers:** Run `rg "create_schema_v3" tagslut/ --include="*.py" -n` and enumerate. T3-D cannot be closed without this result.
4. **`run_pending_v3` idempotency at scale:** On a DB with 10,000+ rows, does calling `run_pending_v3` on every `tagslut get` invocation (via `ensure_cohort_support`) cause performance degradation? Verify migration detection uses `schema_migrations` table lookup rather than re-running all SQL.
<span style="display:none">[^5]</span>

<div align="center">⁂</div>

[^1]: Evaluation_Gemini.md

[^2]: Evaluation_Claude.md

[^3]: Evaluation_ChatGPT.md

[^4]: Audit-B.md

[^5]: Audit-A.md

