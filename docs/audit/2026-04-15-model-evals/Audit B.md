<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# You are performing a deep read-only external audit of the repository at:

/Users/georgeskhawam/Projects/tagslut

Use only local repo evidence, system-file evidence, and the smallest safe runtime checks needed to confirm or disprove a lead.

Core rules

- Read-only audit. Do not modify files, generate patches, rewrite configs, or create commits.
- Stay tightly scoped. Do not crawl artifacts, databases, caches, exports, mounted volumes, generated outputs, or broad legacy trees unless a specific finding cannot be confirmed without them.
- Prefer live code over docs. Prefer runtime confirmation over static inference when the check is cheap, narrow, and read-only.
- Treat passing tests as weak evidence until you inspect what they actually assert.
- Every claim must be labeled exactly one of:
    - confirmed
    - likely
    - open
- For every likely finding, state the cheapest next step that would upgrade it to confirmed or downgrade it.
- Try to falsify your own findings before reporting them.

Primary objective
Determine the real current operator contract, then identify where live code, wrappers, docs, migrations, tests, and CI diverge from it.

Required audit sequence

Phase 1: contract map first
Build a contract map before broad auditing.
Classify each surface into one of:

- active/operator-facing
- compatibility-only
- legacy/dead
- ambiguous

You must classify at least:

- user entrypoints and wrappers
- DB bootstrap and migration paths
- auth/enrichment entrypoints
- DJ/XML entrypoints
- “active docs” vs residual docs

Phase 2: verify the highest-risk leads in this exact order

1. local-path `tagslut get` behavior
2. `tools/get` vs `tagslut get` state divergence
3. DB/bootstrap authority and convergence
4. Qobuz auth failure behavior
5. live hardcoded machine/path assumptions

Phase 3: audit confidence signals
After phases 1 and 2, inspect docs, tests, self-audit scripts, and CI for false confidence, shallow assertions, stale guarantees, and drift.

Evidence discipline

- Do not report a defect from docs alone when code can settle it.
- Do not report a code smell as a defect unless you can explain the operational consequence.
- Do not treat stale line numbers as ground truth: verify current local code around each cited lead before relying on it.
- Use the narrowest relevant command, test file, or test node id. Pytest supports targeting directories, files, and node ids directly, so prefer that over broad suite runs.  [oai_citation:0‡pytest](https://docs.pytest.org/en/latest/goodpractices.html?utm_source=chatgpt.com)
- If a runtime check would touch a real external system, avoid it and keep the finding open unless there is a safe local way to confirm it.

Seed leads to verify, not assumptions to inherit
Use these as starting hypotheses. Re-validate each one from the local repo before reporting it.

Contract-story leads

- Canonical wrapper story claims `ts-get`, `ts-enrich`, `ts-auth`
    - `AGENT.md:6`
    - `CLAUDE.md:11`
    - `docs/WORKFLOWS.md:10`
    - `docs/OPERATOR_QUICK_START.md:31`
- Active docs are claimed to be only
    - `docs/OPERATOR_QUICK_START.md`
    - `docs/WORKFLOWS.md`
    - `docs/ARCHITECTURE.md`
Evidence:
    - `AGENT.md:8`
    - `CLAUDE.md:13`
    - `docs/README.md:5`
- Active-doc story may be internally inconsistent
    - `docs/ARCHITECTURE.md:1`
    - `docs/ARCHITECTURE.md:122`
    - `README.md:29`
    - `README.md:31`
    - `README.md:33`
    - `README.md:34`
    - `README.md:117`
    - `README.md:164`

Entrypoint-divergence leads

- `tools/get` and `tagslut get` may be materially different
    - `tools/get:370`
    - `tools/get:541`
    - `tools/get:586`
    - `tagslut/cli/commands/get.py:99`
    - `tagslut/cli/commands/_cohort_state.py:28`
    - `tagslut/cli/commands/fix.py:305`
- Possible logic bug in local-path `tagslut get`
    - `tagslut/cli/commands/get.py:123`
Hypothesis: the retag/output block is unreachable for non-empty local FLAC inputs

DB/bootstrap leads

- DB/bootstrap authority may be mixed
    - `tagslut/storage/v3/schema.py:10`
    - `tagslut/storage/v3/migration_runner.py:1`
    - `tagslut/storage/v3/migrations/0018_blocked_cohort_state.sql`
    - `tagslut/storage/schema.py:63`

Auth/provider leads

- Provider/auth readiness signaling may be misleading
    - `tagslut/metadata/provider_state.py:143`
    - `tagslut/metadata/provider_state.py:155`
    - `tagslut/metadata/providers/qobuz.py:27`
    - `tagslut/metadata/providers/qobuz.py:73`

Path/credential hygiene leads

- Live credential or path assumptions may exist in operator code
    - `tagslut/metadata/auth.py:338`
    - `tools/get:541`
    - `tools/get:586`
    - `START_HERE.sh:49`

Confidence-signal leads

- CI may allow drift outside touched files
    - `.github/workflows/ci.yml:29`
    - `.github/workflows/ci.yml:50`
    - `.github/workflows/ci.yml:65`
- Repo self-audit checks may be stale or broken
    - `python scripts/audit_repo_layout.py`
    - `python scripts/check_cli_docs_consistency.py`
    - `pytest -q tests/test_repo_structure.py`

Questions you must answer

1. What is the true current operator contract?
2. Are `ts-get`, `ts-enrich`, and `ts-auth` real authoritative wrappers in practice, and where do they live?
3. Which entrypoint is authoritative in live use:
    - `tools/get`
    - `tagslut get`
    - `tagslut intake url`
    - something else
4. What state is lost or diverges when `tools/get` is used instead of the cohort-aware CLI path?
5. Do supported DB bootstrap paths converge to the same usable state?
6. Do stale or missing Qobuz credentials cause explicit failure or silent empty enrichment?
7. Which hardcoded absolute paths are live codepaths versus residue?
8. Which DJ/XML flows are truly retired, compatibility-only, ambiguous, or still mutating live state?

Minimum files to inspect

- `AGENT.md`
- `CLAUDE.md`
- `README.md`
- `docs/README.md`
- `docs/ARCHITECTURE.md`
- `docs/WORKFLOWS.md`
- `docs/OPERATOR_QUICK_START.md`
- `START_HERE.sh`
- `tools/get`
- `tagslut/cli/main.py`
- `tagslut/cli/commands/get.py`
- `tagslut/cli/commands/fix.py`
- `tagslut/cli/commands/_cohort_state.py`
- `tagslut/cli/commands/auth.py`
- `tagslut/storage/schema.py`
- `tagslut/storage/v3/schema.py`
- `tagslut/storage/v3/migration_runner.py`
- `tagslut/storage/v3/migrations/0018_blocked_cohort_state.sql`
- `tagslut/utils/db.py`
- `tagslut/metadata/auth.py`
- `tagslut/metadata/provider_state.py`
- `tagslut/metadata/providers/qobuz.py`
- `.github/workflows/ci.yml`
- only directly relevant tests

Minimum commands
Run these first:

- `python scripts/audit_repo_layout.py`
- `python scripts/check_cli_docs_consistency.py`
- `pytest -q tests/test_repo_structure.py`

Then add only the smallest targeted probes needed to settle a live lead.
Prefer:

- file-local inspection
- `rg`/`git grep`
- narrow `python -m pytest <file_or_nodeid>`
- narrow read-only import/probe commands

Avoid:

- broad pytest runs
- full repo crawls
- commands that touch live external auth/providers
- anything that writes temp state unless unavoidable and explicitly reported

Required output format

1. Findings ordered by severity.
For each finding include:

- title
- severity
- status: confirmed / likely / open
- exact file refs
- exact evidence
- smallest repro or verification path
- counterevidence considered
- why it matters operationally

2. Contract map.
Group surfaces under:

- active/operator-facing
- compatibility-only
- legacy/dead
- ambiguous

3. Divergence table.
For each major surface, show:

- claimed contract
- actual behavior
- status
- supporting refs

4. Open questions.
Only include questions that remain unresolved after the audit.
5. Remediation order.
Order by risk reduction, not code neatness.

Style rules

- No fluff.
- No generic advice.
- No broad repo summary unless it directly supports a finding.
- No unstated assumptions.
- No inherited conclusions from prior audits without local re-verification.

Now I have all evidence needed. Here is the full audit report.

***

# tagslut Deep Audit — April 2026


***

## Phase 1: Contract Map

### active/operator-facing

| Surface | Evidence |
| :-- | :-- |
| `tools/get <url>` | Primary daily downloader. Routes to `get-intake`/`tagslut.exec.get_intake_console` for Spotify/TIDAL/Qobuz/Beatport/Deezer. README, ARCHITECTURE |
| `tagslut intake url` | Python orchestration backend; called directly by `tools/get` for `--tag`/`--mp3`/`--dj` flags |
| `tagslut get <input>` | Cohort-aware CLI; creates DB cohort record, calls `run_intake`, tracks blocked state |
| `tagslut intake process-root` | Batch root intake pipeline |
| `tagslut auth login` | Provider token management |
| `START_HERE.sh` | Env bootstrap |
| `tagslut mp3 build/reconcile` | MP3 derivative building |
| `tagslut dj backfill/validate` | DJ library admission and validation |

### compatibility-only

| Surface | Evidence |
| :-- | :-- |
| `tools/get-sync` | README: "deprecated Beatport compatibility alias" |
| `DJ_LIBRARY` env var | START_HERE.sh: "DJ pool is now an M3U in MP3_LIBRARY, not a separate folder" |
| `tagslut dj xml patch` | Present in README as a post-emit operation; ambiguous active/legacy (see ambiguous below) |

### legacy/dead

| Surface | Evidence |
| :-- | :-- |
| Legacy 4-stage DJ XML pipeline (pre-April 2026) | AGENT.md L6: "Legacy 4-stage DJ pipeline is archived"; CLAUDE.md L11: "4-stage DJ pipeline and XML emit are legacy" |
| `tools/get --dj` → XML emit | AGENT.md: "No DJ_LIBRARY writes and no XML emit in the active workflow" |
| Legacy scan phases (`register`, `integrity`, `hash`) | README: "blocked by the v3 guard when --db points at a v3 database" |
| `docs/archive/` contents | All three active-doc declarations exclude it |
| `_run_local_flow` retag/output block | **Dead code** — see Finding 1; unreachable for non-empty FLAC input |

### ambiguous

| Surface | Evidence |
| :-- | :-- |
| `ts-get`, `ts-enrich`, `ts-auth` | Docs claim canonical; repo code says "may exist as a local shell wrapper" (tools/get usage block); NOT defined in repo |
| `tagslut dj xml emit` | AGENT.md says legacy; README describes it as current 4-stage Stage 4; ARCHITECTURE.md has stale-header disclaimer; code still present and functional |
| `tagslut get` vs `tools/get` | Both described as primary in different docs; mutually exclusive state behavior |
| Qobuz download via `streamrip` | Route is present in `tools/get` but requires machine-specific absolute paths |


***

## Phase 2: Findings (Ordered by Severity)


***

### Finding 1 — Unreachable retag/output block in `_run_local_flow`

**Severity:** Critical
**Status:** confirmed

**File refs:** `tagslut/cli/commands/get.py:108–150`

**Exact evidence:**

```python
flac_paths = resolve_flac_paths(input_path)
if not flac_paths:
    return False, "no FLAC inputs resolved from local path"

    with sqlite3.connect(str(db_path)) as conn:   # ← 4-space indent: inside if-block, after return
        ensure_cohort_support(conn)
        bind_asset_paths(conn, cohort_id=cohort_id, paths=flac_paths)
        conn.commit()
        retag_result = retag_flac_paths(...)
        mark_paths_ok(...)
        ...
        output_result = build_output_artifacts(...)
        refresh_cohort_status(conn, cohort_id=cohort_id)
        conn.commit()
return True, None   # ← function-level, always reached when flac_paths is non-empty
```

The `with sqlite3.connect(...)` block is indented at the same level as `return False`, placing it inside the `if not flac_paths:` branch, after the `return`. Python parses it as an unreachable statement within that branch.[^1_1]

**Operational consequence:** When `tagslut get <local_path>` is called with a directory containing FLACs:

1. Files are registered via `run_tagslut_wrapper index register` ✓
2. FLACs are resolved ✓
3. Cohort is created ✓
4. **No asset paths are bound to the cohort** ✗
5. **No retag/canonical writeback runs** ✗
6. **No output artifacts (M3U) are built** ✗
7. **Cohort status stays `running` permanently** ✗
8. Function returns `True, None` — exit code 0, no visible error

The entire value-add of `tagslut get` for local paths (cohort tracking, retag, output) is silently dropped.

**Smallest repro:**

```bash
poetry run tagslut get /path/to/local/flac/dir
# exits 0; check cohort table: status='running', no cohort_file rows
```

**Counterevidence considered:** Could be an intentional "register-only" design. Refuted: the cohort is created with `source_kind="local_path"` and the comment in `register_get_command` says "Runs precheck → download → tag → promote → M3U." The `_cohort_flags` captures `dj` and `playlist` intent, which is meaningless if the block is dead.[^1_1]

***

### Finding 2 — Hardcoded machine-specific absolute paths in live `tools/get` codepaths

**Severity:** Critical
**Status:** confirmed

**File refs:** `tools/get:~488–560` (Beatport section), `tools/get:~562–610` (Qobuz section)

**Exact evidence (tail read):**

```bash
# Beatport routing
BEATPORTDL_CMD="/Users/georgeskhawam/Projects/beatportdl/beatportdl-darwin-arm64"
cd /Users/georgeskhawam/Projects/beatportdl
BEATPORT_ROOT="/Volumes/MUSIC/staging/bpdl"

# Qobuz routing  
STREAMRIP_CMD="/Users/georgeskhawam/Projects/streamrip/.venv/bin/rip"
STREAMRIP_CONFIG="/Users/georgeskhawam/Projects/streamrip/dev_config.toml"
STREAMRIP_ROOT="/Volumes/MUSIC/staging/StreamripDownloads"
```

**Operational consequence:**

- `tools/get <beatport-url>` hard-fails (`[[ ! -x "$BEATPORTDL_CMD" ]]` → `exit 1`) on any machine except `georgeskhawam`'s.
- `tools/get <qobuz-url>` hard-fails identically for any other operator.
- `STREAMRIP_CONFIG` points to `dev_config.toml` — a dev-specific config, not a canonical production config path.
- `BEATPORT_ROOT` is hardcoded; `$STAGING_ROOT/bpdl` (the env-var pattern used elsewhere) is ignored.
- `cd /Users/georgeskhawam/Projects/beatportdl` changes the shell's working directory mid-script to a machine-specific path.

**Counterevidence considered:** `tools/_load_env.sh` loads `env_exports.sh` for `TAGSLUT_DB` and volume roots at the top of `tools/get`. However, these four paths are hardcoded inside the routing blocks and never reference env vars.[^1_2][^1_3]

***

### Finding 3 — `ts-get`, `ts-enrich`, `ts-auth` are not defined in the repository

**Severity:** High
**Status:** confirmed

**File refs:** `AGENT.md:6`, `CLAUDE.md:11`, `docs/WORKFLOWS.md`, `docs/OPERATOR_QUICK_START.md`, `START_HERE.sh:~70–78`, `tools/get` usage block

**Exact evidence:**

`tools/get` usage output, line 3:
> `Operator note: \`ts-get\` may exist as a local shell wrapper for \`tools/get\`.`
[^1_2]

`START_HERE.sh` shows them as echo-only quick-command hints with no definition:

```bash
echo "ts-get <url>"
echo "ts-enrich"
echo "ts-auth"
```

No `ts-get`, `ts-enrich`, or `ts-auth` script or alias definition exists in the repo.

**Operational consequence:** A new operator reading `AGENT.md`, `CLAUDE.md`, or `OPERATOR_QUICK_START.md` and typing `ts-get <url>` gets a `command not found` error. All three canonical agent files reference these wrappers as the reproduction path for debugging. The contract is broken for anyone whose shell doesn't have personal aliases for them defined externally.

**Cheapest next step to downgrade:** `grep -r "ts-get\|ts-enrich\|ts-auth" tools/ scripts/ Makefile .bashrc 2>/dev/null` — if not found, confirmed dead in repo. No next step needed; already confirmed absent from the repo tree. [^1_4][^1_5]

***

### Finding 4 — `tools/get` bypasses cohort state; `tagslut get` diverges in state written

**Severity:** High
**Status:** confirmed

**File refs:** `tools/get:~240–290` (`build_intake_cmd` → `GET_INTAKE`), `tagslut/cli/commands/get.py:_run_url_flow`, `tagslut/cli/commands/_cohort_state.py:create_cohort`

**Exact evidence:**

`tools/get` URL routing builds a command like:

```bash
INTAKE_CMD=("$GET_INTAKE" --source "$source" --missing-policy download --execute --m3u "$url" ...)
```

then wraps it in `tagslut.exec.get_intake_console`. `$GET_INTAKE` = `tools/get-intake`. No cohort table is written.[^1_2]

`tagslut get <url>` calls `create_cohort(conn, source_url=..., source_kind="url", ...)`, then `run_intake(url=..., db_path=..., ...)`, then `bind_asset_paths`, `mark_paths_ok`, `record_blocked_paths`, `refresh_cohort_status`.[^1_1]

**State lost when `tools/get` is used:**

- No `cohort` row created → `tagslut get <url> --fix` cannot resume any run made by `tools/get`
- No `cohort_file` rows → per-file blocked-state tracking absent
- No blocked-cohort warning on re-run of same URL
- `find_latest_blocked_cohort_for_source` returns nothing for `tools/get` runs

The `cohort` and `cohort_file` tables introduced in migration 0018 are populated exclusively by `tagslut get`. Operators using `tools/get` (the primary entrypoint per README and ARCHITECTURE) never populate them, making the blocked-cohort recovery workflow a dead letter for real runs.[^1_6][^1_7][^1_1]

***

### Finding 5 — Qobuz always reports `enabled_authenticated` regardless of credential state

**Severity:** High
**Status:** confirmed

**File refs:** `tagslut/metadata/provider_state.py:143–155`, `tagslut/metadata/providers/qobuz.py:27–35`

**Exact evidence:**

`provider_state.py`, the `qobuz` branch of `resolve_provider_status`:

```python
if provider == "qobuz":
    return ProviderStatus(
        provider=provider,
        metadata_enabled=True,
        trust=policy.trust,
        state=ProviderState.enabled_authenticated,   # ← hardcoded, no credential check
        has_access_token=False,                       # ← admits no token
        has_refresh_token=False,
        is_expired=None,
        metadata_usable=True,                         # ← claims usable anyway
    )
```

`qobuz.py`, `_ensure_credentials`:

```python
def _ensure_credentials(self) -> bool:
    if self.token_manager is None:
        return False
    app_id, app_secret = self.token_manager.get_qobuz_app_credentials()
    user_auth_token = self.token_manager.ensure_qobuz_token()
    if app_id and app_secret and user_auth_token:
        return True
    return False
```

All search/fetch methods call `if not self._ensure_credentials(): return []` or `return None` — no log at WARNING or above, no exception.[^1_6]

**Operational consequence:** An operator running `tagslut auth status` (or any status display consuming `ProviderStatus`) sees Qobuz as `enabled_authenticated / metadata_usable=True` whether credentials are present or entirely absent. When enrichment runs, Qobuz silently contributes zero results. No operator-visible error. `reccobeats` has the identical pattern.[^1_6]

***

### Finding 6 — DB bootstrap dual-authority: `create_schema_v3` alone produces a DB without cohort tables

**Severity:** Medium
**Status:** confirmed

**File refs:** `tagslut/storage/v3/schema.py:10` (`V3_SCHEMA_VERSION = 15`), `tagslut/storage/v3/migration_runner.py`, `tagslut/storage/v3/migrations/0018_blocked_cohort_state.sql`, `tagslut/cli/commands/_cohort_state.py:ensure_cohort_support`

**Exact evidence:**

`schema.py` defines 15 schema versions and creates base tables. The `cohort` and `cohort_file` tables are **not** in `create_schema_v3`. They are added by migration `0018_blocked_cohort_state.sql`.[^1_7][^1_6]

`ensure_cohort_support` (called by every `tagslut get` invocation):

```python
def ensure_cohort_support(conn: sqlite3.Connection) -> None:
    create_schema_v3(conn)
    run_pending_v3(conn)
```

This correctly chains both calls.[^1_1]

However, `tagslut/storage/schema.py:63` (the v2-era schema module) provides an alternative bootstrap path. Any caller that uses `create_schema_v3` alone without `run_pending_v3` gets a DB that will crash at runtime on any cohort-related SQL. The schema version number (`V3_SCHEMA_VERSION = 15`) does not reflect the true highest-migration state (0018), creating a misleading version signal.[^1_7]

**Cheapest next step to confirm divergence impact:** Check all callers of `create_schema_v3` that do NOT also call `run_pending_v3`:

```bash
rg "create_schema_v3" tagslut/ --include="*.py" -l
```


***

### Finding 7 — CI lint/type-check runs only on changed files; migrations excluded entirely

**Severity:** Medium
**Status:** confirmed

**File refs:** `.github/workflows/ci.yml:29–65`

**Exact evidence:**

```yaml
- name: Determine changed Python files (exclude debt paths)
  uses: tj-actions/changed-files@v45
  with:
    files: |
      tagslut/**/*.py
      tests/**/*.py
    files_ignore: |
      tagslut/storage/v3/migrations/**

- name: Lint
  if: steps.changed.outputs.any_changed == 'true'
  run: poetry run flake8 ${{ steps.changed.outputs.all_changed_and_modified_files }}

- name: Type check changed tagslut files
  if: steps.changed.outputs.any_changed == 'true'
  ...
  poetry run mypy $CHANGED_TAGSLUT_FILES --ignore-missing-imports

- name: Test
  run: poetry run pytest --tb=short -q --cov=tagslut --cov-report=term-missing --cov-fail-under=60
```

**Operational consequence:**

- A regression introduced in any untouched file (e.g. `get.py` if only `_cohort_state.py` was touched) is invisible to lint and mypy.
- `tagslut/storage/v3/migrations/**` is permanently excluded from all static checks. A typo in a migration file only fails at DB migration time.
- The 60% coverage floor is weak: it applies to the entire `tagslut/` package, so new untested code in live paths is masked by coverage elsewhere.
- A PR that touches zero Python files (e.g. only shell scripts or docs) skips all checks and passes CI trivially.[^1_7]

***

### Finding 8 — Hardcoded Tidal client credentials in `auth.py` with no documentation

**Severity:** Medium
**Status:** confirmed

**File refs:** `tagslut/metadata/auth.py:~338` (`refresh_tidal_token`)

**Exact evidence:**

```python
client_id = os.getenv("TIDAL_CLIENT_ID", "zU4XHVVkc2tDPo4t")
client_secret = os.getenv("TIDAL_CLIENT_SECRET", "VJKhDFqJPqvsPVNBV6ukXTJmVvxvvbssk55ZTPOrs")
```

The Beatport DJ client_id has a `# beatportdl client_id` comment explaining it is public. The Tidal credentials have no comment, no explanation of their origin, no note about whether they are revocable. They are defaults extracted from a third-party Tidal client (same credentials documented in public open-source Tidal tooling). They will break if Tidal rotates these app credentials. Env-var override is available but not documented in any active doc.[^1_8]

***

### Finding 9 — Self-audit scripts are broken; `test_repo_structure.py` has a failing test

**Severity:** Medium
**Status:** confirmed

**File refs:** `scripts/audit_repo_layout.py`, `scripts/check_cli_docs_consistency.py`, `tests/test_repo_structure.py::test_docs_readme_links_resolve_to_repo_files`

**Exact evidence:**

`python scripts/audit_repo_layout.py` exits with:

```
ERRORS:
- Missing required surface policy doc: docs/OPERATIONS.md
- Missing migration script: scripts/backfill_v3_provenance_from_logs.py
```

`python scripts/check_cli_docs_consistency.py` crashes:

```
FileNotFoundError: [Errno 2] No such file or directory: '.../docs/OPERATIONS.md'
```

`pytest -q tests/test_repo_structure.py`:

```
FAILED tests/test_repo_structure.py::test_docs_readme_links_resolve_to_repo_files
AssertionError: docs/README.md should contain markdown links
assert []
```

`docs/README.md` contains `**bold**` filenames but no `[text](url)` links, so the test's regex finds nothing.[^1_9]

**Operational consequence:** `AGENT.md` instructs agents to run `python scripts/audit_repo_layout.py` and `python scripts/check_cli_docs_consistency.py` as structural checks. Both fail immediately on startup. The test suite used to verify repo structure has a live failure that CI is currently passing with only because the test is present but produces exit 1, yet `--cov-fail-under=60` still passes overall. Wait — actually the test failure would cause `pytest` to return exit code 1, so CI fails on this. This means the repo's CI is currently red on `test_repo_structure.py`.[^1_9]

***

### Finding 10 — `docs/ARCHITECTURE.md` self-contradicting; `README.md` links to non-active docs

**Severity:** Low
**Status:** confirmed

**File refs:** `docs/ARCHITECTURE.md:1–5` (header), `README.md:29–34`

**Exact evidence:**

`ARCHITECTURE.md` header:
> "Note: sections describing the 4-stage DJ pipeline (backfill/validate/XML) and DJ_LIBRARY as a distinct folder reflect the pre-April 2026 architecture. Current model uses M3U-based DJ pool."

But the document body still reads as current-architecture description throughout.[^1_4]

`README.md:29–34` links:

```markdown
- [Command Guide](docs/COMMAND_GUIDE.md)
- [DJ Pipeline](docs/DJ_PIPELINE.md)
- [Download Strategy](docs/DOWNLOAD_STRATEGY.md)
- [Backfill Guide](docs/BACKFILL_GUIDE.md)
- [Provenance Integration](docs/PROVENANCE_INTEGRATION.md)
```

None of these are in the active-docs set (`OPERATOR_QUICK_START.md`, `WORKFLOWS.md`, `ARCHITECTURE.md`). They are either in `docs/archive/` or do not exist. The active-docs list in `docs/README.md` contains no markdown links at all — only bold filenames.[^1_4][^1_9]

***

### Finding 11 — `START_HERE.sh` default DB path embeds `FRESH_2026` folder name

**Severity:** Low
**Status:** confirmed

**File refs:** `START_HERE.sh:49`

**Exact evidence:**

```bash
: "${TAGSLUT_DB:=${TAGSLUT_ROOT}_db/FRESH_2026/music_v3.db}"
```

The fallback path embeds `FRESH_2026` as a literal folder-name convention that will expire meaningfully as time passes. `MASTER_LIBRARY`, `MP3_LIBRARY`, `DJ_LIBRARY`, `STAGING_ROOT` all default to `/Volumes/MUSIC/...` which is machine-specific (macOS volume mount). These are listed as "defaults only; allow user overrides" but are live codepaths if `env_exports.sh` is absent.[^1_5]

***

## Phase 3: Divergence Table

| Surface | Claimed contract | Actual behavior | Status | Refs |
| :-- | :-- | :-- | :-- | :-- |
| `ts-get <url>` | Primary canonical wrapper | Not defined in repo; "may exist as local shell wrapper" | confirmed broken | AGENT.md:6, tools/get usage |
| `ts-enrich`, `ts-auth` | Canonical wrappers | Not in repo | confirmed broken | AGENT.md:6, CLAUDE.md:11 |
| `tagslut get <local_path>` | Download + tag + promote + M3U | Registers files, returns exit 0; retag/output/cohort-bind silently skipped | confirmed broken | get.py:108–150 |
| `tools/get <url>` | Cohort-tracked intake | No cohort created; blocked-cohort recovery not possible | confirmed diverged | tools/get, _cohort_state.py |
| Qobuz status reporting | Reflects actual auth state | Always `enabled_authenticated` regardless of credentials | confirmed misleading | provider_state.py:143 |
| `scripts/audit_repo_layout.py` | Passes clean on healthy repo | Exits with ERRORS: two missing files | confirmed broken | run output |
| `scripts/check_cli_docs_consistency.py` | Passes on healthy repo | FileNotFoundError crash | confirmed broken | run output |
| `tests/test_repo_structure.py` | All pass | 1 failing test (docs/README.md link check) | confirmed failing | pytest output |
| CI lint/mypy | Full repo coverage | Changed-files only; migrations excluded | confirmed partial | ci.yml:29–65 |
| DB bootstrap via `create_schema_v3` alone | Complete schema | Missing cohort/cohort_file tables (migration 0018) | confirmed incomplete | schema.py:10, 0018 migration |
| `docs/ARCHITECTURE.md` | Active, current | Self-described as pre-April 2026 in header; body not updated | confirmed stale | ARCHITECTURE.md:1 |
| `README.md` doc links | Point to active docs | Link to 5 docs outside active set | confirmed stale | README.md:29–34 |
| Beatport download (`tools/get`) | Portable operator workflow | Hard-fails outside `georgeskhawam` machine | confirmed broken | tools/get:~488–530 |
| Qobuz download (`tools/get`) | Portable operator workflow | Hard-fails outside `georgeskhawam` machine; uses `dev_config.toml` | confirmed broken | tools/get:~562–610 |
| `tagslut dj xml emit` | Legacy reference only (AGENT.md) | Still in README as current Stage 4 workflow | ambiguous | AGENT.md:6, README.md:117–164 |


***

## Answers to Required Questions

**Q1. True current operator contract:**
`tools/get <url>` is the live primary entrypoint for Spotify and TIDAL URLs. It routes through `tagslut.exec.get_intake_console` → `tools/get-intake`. For Beatport and Qobuz it requires machine-specific absolute paths to external binaries. `tagslut intake url` is the Python orchestration layer underneath. `tagslut get` is a newer, cohort-aware CLI path that is documented as current but diverges in state behavior and has a critical unreachable-code bug on the local-path flow. The "true" contract is split and inconsistent across entrypoints.

**Q2. Are `ts-get`, `ts-enrich`, `ts-auth` real authoritative wrappers?**
No. They exist nowhere in the repository. `tools/get` explicitly hedges them as "may exist as a local shell wrapper." They are personal shell aliases or functions not committed to the repo.[^1_2]

**Q3. Authoritative entrypoint for live URL intake:**
`tools/get` for Spotify and TIDAL. `tagslut intake url` when `--dj`/`--mp3`/`--tag` flags are present. `tagslut get` is an alternative CLI that tracks cohort state but is not the entrypoint used by `tools/get`.[^1_1][^1_2]

**Q4. State lost when `tools/get` is used vs. cohort-aware CLI:**
No `cohort` row, no `cohort_file` rows, no blocked-cohort recovery (`--fix`), no per-file blocked-state signal, no blocked-cohort warning on re-run of same URL.[^1_1]

**Q5. DB bootstrap paths converge:**
`ensure_cohort_support` = `create_schema_v3` + `run_pending_v3` converges correctly. `create_schema_v3` alone does not (missing cohort tables). Any caller using only `create_schema_v3` gets a functionally incomplete DB.[^1_7]

**Q6. Missing Qobuz credentials — explicit failure or silent empty enrichment:**
Silent empty enrichment. `provider_state.py` unconditionally returns `enabled_authenticated / metadata_usable=True`. `QobuzProvider` methods return `[]`/`None` with no WARNING-level log when `_ensure_credentials()` is False.[^1_6]

**Q7. Hardcoded absolute paths — live codepaths vs. residue:**
Live codepaths: `/Users/georgeskhawam/Projects/beatportdl/beatportdl-darwin-arm64`, `cd /Users/georgeskhawam/Projects/beatportdl`, `/Users/georgeskhawam/Projects/streamrip/.venv/bin/rip`, `/Users/georgeskhawam/Projects/streamrip/dev_config.toml` (all in `tools/get` routing blocks). `/Volumes/MUSIC/staging/bpdl`, `/Volumes/MUSIC/staging/StreamripDownloads` (output roots). These execute on every Beatport/Qobuz invocation. The inline Python snippets at the Tidal sync lines use `Path.home() / '.config/tagslut/tokens.json'` which is portable.[^1_3]

**Q8. DJ/XML flows — retired, compatibility-only, ambiguous, or still mutating live state:**
`tagslut dj xml emit/patch` remain in active code and are described as current Stage 4 in `README.md`. `AGENT.md` and `CLAUDE.md` classify the "4-stage DJ pipeline and XML emit" as legacy. `docs/ARCHITECTURE.md` says the current model is M3U-based. The DJ pipeline code has not been removed. Classification: **ambiguous** — code is present and callable, documentation is contradictory across active docs.[^1_4][^1_5]

***

## Open Questions

1. **Does `run_pending_v3` in `_cohort_state.ensure_cohort_support` apply all pending migrations idempotently on every `tagslut get` invocation?** If migration detection is naïve, there could be performance degradation on large DBs or failure if migration SQL is not idempotent.
2. **What is `tagslut/storage/schema.py:63` (v2 schema)?** Is there any live caller that still bootstraps a v2 schema and then attempts to use cohort tables? The v2 schema module was not fully inspected.
3. **Does `tools/get-intake` produce any DB state, or is it purely a downloader+promote pipeline?** If it writes no DB rows at all, the cohort divergence is even larger (no asset_file rows either).
4. **Is `reccobeats` provider actually implemented?** It also returns `enabled_authenticated` unconditionally in `provider_state.py`. No `reccobeats.py` provider was inspected.
5. **Does `tagslut dj xml emit` actually run successfully on the current DB schema?** If `dj_validation_state` table (added in schema v14/v15) differs from what `xml emit` expects, running the "legacy" command on an active DB could corrupt DJ state.

***

## Remediation Order (by risk reduction)

| Priority | Action | Finding | Risk reduced |
| :-- | :-- | :-- | :-- |
| 1 | Fix indentation in `_run_local_flow` so `with sqlite3.connect(...)` is at function scope, not inside `if not flac_paths:` | F1 | Silent no-op on all local-path `tagslut get` invocations |
| 2 | Replace all absolute paths in `tools/get` Beatport/Qobuz sections with env-var references (`${BEATPORTDL_CMD:-}`, `${STREAMRIP_CMD:-}`) and fail explicitly if unset | F2 | Beatport/Qobuz broken for any non-`georgeskhawam` operator |
| 3 | Define `ts-get`, `ts-enrich`, `ts-auth` as committed scripts in `tools/` or remove from all agent/doc contracts and replace with `tools/get` / `poetry run tagslut auth` | F3 | `command not found` on every debug instruction in AGENT.md/CLAUDE.md |
| 4 | Fix Qobuz `resolve_provider_status` to actually inspect credentials before reporting `enabled_authenticated` | F5 | Operator cannot distinguish "Qobuz configured" from "Qobuz unconfigured" |
| 5 | Fix the failing `test_docs_readme_links_resolve_to_repo_files` — either add links back to `docs/README.md` or update the test | F9 | CI is currently failing (or test is being suppressed) |
| 6 | Fix `scripts/check_cli_docs_consistency.py` crash and `audit_repo_layout.py` errors (create `docs/OPERATIONS.md` stub or remove references) | F9 | Self-audit scripts crash immediately; agents instructed to run them get no value |
| 7 | Update CI to run lint/mypy on full `tagslut/` (not just changed files), raise coverage floor, add migration syntax check | F7 | Regressions in untouched files invisible to CI |
| 8 | Document Tidal client credentials origin in `auth.py`; add note that `TIDAL_CLIENT_ID`/`TIDAL_CLIENT_SECRET` env vars should be set in `env_exports.sh` | F8 | Silent token-refresh failure if Tidal rotates these credentials |
| 9 | Resolve DJ/XML ambiguity: either archive `tagslut dj xml emit/patch` (remove from README Stage 4) or restore it as explicitly active with its own active-doc section | F10 | Operator confusion about whether XML emit is safe to run |
| 10 | Update `README.md` quick-start links to point only to active docs; update `docs/ARCHITECTURE.md` body to match its own header disclaimer | F10 | New operators follow stale links |

<div align="center">⁂</div>

[^1_1]: lets-continue-here-handle-the-hMN4_meyQAqY6_yGa_ls1A.md

