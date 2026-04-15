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

The repo does not currently present one stable operator contract. The strongest local evidence shows a wrapper-first, M3U-pool story in `AGENT.md`, `CLAUDE.md`, `docs/README.md`, and `docs/OPERATOR_QUICK_START.md`, while `README.md` and `docs/ARCHITECTURE.md` still present `tools/get` and a DB-backed DJ/XML pipeline as supported operator paths.[^1_1][^1_2]

## Findings

### 1) Split operator contract between wrapper-first docs and `tools/get`/DJ-XML docs

- severity: high[^1_2][^1_1]
- status: confirmed[^1_1][^1_2]
- exact file refs: `AGENT.md:6-12`, `CLAUDE.md:11-13`, `docs/README.md:5-9`, `docs/OPERATOR_QUICK_START.md:13-18,31-43`, `README.md:81-108,110-123,164`, `docs/ARCHITECTURE.md:1-4,30-39,107-133`.[^1_2][^1_1]
- exact evidence: `AGENT.md` and `CLAUDE.md` call `ts-get`, `ts-enrich`, and `ts-auth` the active wrappers, say the DJ pool is M3U-based, and say the 4-stage DJ pipeline and Rekordbox XML are legacy/archive material. `docs/README.md` reinforces that only `OPERATOR_QUICK_START.md`, `WORKFLOWS.md`, and `ARCHITECTURE.md` are active docs. `docs/OPERATOR_QUICK_START.md` tells operators to use `ts-auth`, `ts-get`, and `ts-enrich`. In direct conflict, `README.md` says `tools/get` is the “primary user-facing downloader” and says the curated DJ pipeline ending in `tagslut dj xml emit` or `patch` is the “only supported workflow.” `docs/ARCHITECTURE.md` simultaneously says “Use `tools/get` for day-to-day provider intake,” labels `tools/get --dj` compatibility-only later, and still calls the DB-backed DJ path canonical.[^1_1][^1_2]
- smallest repro or verification path: read the cited docs side by side; no runtime step is needed because the contradiction is explicit in the checked-in text.[^1_2][^1_1]
- counterevidence considered: `README.md` does say `tools/get --mp3` and `--dj` route to canonical `tagslut intake url`, which partially aligns with a CLI-centered story, but that does not reconcile the conflicting claims about plain `tools/get` or about whether DJ/XML is legacy versus supported.[^1_2]
- why it matters operationally: operators can choose materially different entrypoints for the same job and receive different state tracking, output, and support expectations.[^1_1][^1_2]


### 2) Local confidence checks are stale and currently failing on repo layout drift

- severity: high[^1_1]
- status: confirmed[^1_1]
- exact file refs: `scripts/audit_repo_layout.py`, `scripts/check_cli_docs_consistency.py`, `tests/test_repo_structure.py`, `docs/README.md`.[^1_1]
- exact evidence: `python scripts/audit_repo_layout.py` reports missing `docs/OPERATIONS.md` and missing `scripts/backfill_v3_provenance_from_logs.py`. `python scripts/check_cli_docs_consistency.py` then crashes with `FileNotFoundError` on `docs/OPERATIONS.md`. `pytest -q tests/test_repo_structure.py` fails because `tests/test_repo_structure.py::test_docs_readme_links_resolve_to_repo_files` expects markdown links in `docs/README.md`, but the current `docs/README.md` is a plain bullet list with no links.[^1_1]
- smallest repro or verification path: rerun the three baseline commands already executed above; they fail without touching external systems.[^1_1]
- counterevidence considered: 26 tests in `tests/test_repo_structure.py` still pass, but the failing link test and the crashing consistency script show the confidence layer is already out of sync with the current docs shape.[^1_1]
- why it matters operationally: the repo’s own audit signals cannot currently distinguish real regressions from stale assumptions, so both humans and CI can get false assurance or noisy breakage.[^1_1]


### 3) `tagslut get` is the only locally confirmed cohort-aware intake path; `tools/get` likely diverges from that state model

- severity: high[^1_2][^1_1]
- status: likely[^1_2][^1_1]
- exact file refs: `tagslut/cli/commands/get.py:15,259-267,296,328,335`, `tagslut/cli/commands/fix.py:280-318`, `tagslut/cli/commands/_cohort_state.py:114,484`, `README.md:106-108`, `docs/ARCHITECTURE.md:30-39,133`.[^1_2][^1_1]
- exact evidence: the captured code references show `tagslut/cli/commands/get.py` imports blocked-cohort helpers, exposes `--fix`, looks up the latest blocked cohort for a source, and explicitly rejects `--fix` on a local path. `tagslut/cli/commands/fix.py` is built around resuming blocked cohorts, and `_cohort_state.py` contains the cohort-state primitives. In the same audit grep, `tools/get` showed no `blocked_cohort` hits at all, while `README.md` says only `tools/get --mp3` and `tools/get --dj` route to canonical `tagslut intake url`, which leaves plain `tools/get` looking non-cohort-aware unless it delegates elsewhere invisibly.[^1_2][^1_1]
- smallest repro or verification path: inspect `tools/get` dispatch around the cited branches (`tools/get:370,541,586`) and confirm the exact command it shells out to for plain URL intake; a no-network `--help` or command-construction-only path would be enough to upgrade this to confirmed or downgrade it.[^1_1]
- counterevidence considered: `README.md` and `docs/ARCHITECTURE.md` still present `tools/get` as a wrapper over multiple phases, so it may delegate more than the current grep surface shows. The present evidence is enough to show asymmetry around blocked-cohort handling, but not enough to prove full state loss across every branch.[^1_2][^1_1]
- why it matters operationally: if operators use `tools/get` for normal intake and `tagslut get` for repair/resume, blocked-cohort recovery and cohort-aware fix flows can drift or disappear depending on entrypoint choice.[^1_2][^1_1]
- cheapest next step: read `tools/get` at the cited dispatch lines and compare its default URL path to the `tagslut get`/`tagslut intake url` path selection.[^1_1]


### 4) Hardcoded machine and volume assumptions remain live in operator-facing bootstrap surfaces

- severity: medium[^1_2][^1_1]
- status: confirmed[^1_2][^1_1]
- exact file refs: `docs/OPERATOR_QUICK_START.md:6,25,31-43`, `START_HERE.sh:50-53,86-90,98-124`, `README.md:101-103,120-123`, `docs/ARCHITECTURE.md:118,160`.[^1_2][^1_1]
- exact evidence: `docs/OPERATOR_QUICK_START.md` tells the operator to `cd /Users/georgeskhawam/Projects/tagslut`. `START_HERE.sh` exports `/Volumes/MUSIC/...` defaults for `MASTER_LIBRARY`, `MP3_LIBRARY`, `DJ_LIBRARY`, and `STAGING_ROOT`, and warns that some operations will fail if `/Volumes/MUSIC` is not mounted. `README.md` also bakes in `/Volumes/MUSIC/_work/...` defaults, and `docs/ARCHITECTURE.md` still names `/Volumes/MUSIC/MP3_LIBRARY_CLEAN` as the candidate universe for a DJ-seed tool.[^1_1][^1_2]
- smallest repro or verification path: read the cited bootstrap/doc lines; no runtime check is needed because the absolute paths are literal.[^1_2][^1_1]
- counterevidence considered: some of these are environment defaults or documentation examples rather than guaranteed code execution on every command, but `START_HERE.sh` is explicitly operator bootstrap material, so those assumptions are live for the advertised workflow.[^1_1][^1_2]
- why it matters operationally: portability is reduced and operator success depends on one workstation layout and one mounted-volume convention even before any provider logic runs.[^1_2][^1_1]


### 5) Local-path `tagslut get` bug hypothesis is not settled by the captured evidence

- severity: medium[^1_1]
- status: open[^1_1]
- exact file refs: `tagslut/cli/commands/get.py:99,123,328`.[^1_1]
- exact evidence: the captured references prove that `tagslut get` has a distinct local-path branch and that `--fix` is invalid on a local path, but the suspected unreachable retag/output block at line 123 was not visible in the retrieved excerpt.[^1_1]
- smallest repro or verification path: inspect `tagslut/cli/commands/get.py` lines 90-150, then run the narrowest pure-local probe against a known FLAC path only if the code remains ambiguous.[^1_1]
- counterevidence considered: none strong enough was captured; the current record is incomplete rather than contradictory.[^1_1]
- why it matters operationally: if the local-path retag/output branch is dead, operators can believe a local-file intake path is producing tagged output when it is not.[^1_1]


### 6) DB/bootstrap authority is mixed in repo structure, but convergence was not locally proven here

- severity: medium[^1_2][^1_1]
- status: open[^1_2][^1_1]
- exact file refs: `tagslut/storage/schema.py`, `tagslut/storage/v3/schema.py`, `tagslut/storage/v3/migration_runner.py`, `tagslut/storage/v3/migrations/0018_blocked_cohort_state.sql`, `scripts/audit_repo_layout.py`.[^1_2][^1_1]
- exact evidence: the audited file set contains both legacy and v3 schema surfaces, and the layout audit is already expecting a missing backfill migration-side script, which is one concrete sign that the bootstrap/migration story is not cleanly self-consistent. The captured output, however, did not include enough of the actual schema/bootstrap code to prove whether supported bootstrap paths converge to one usable DB state.[^1_2][^1_1]
- smallest repro or verification path: compare the actual bootstrap entrypoints in `tagslut/storage/schema.py`, `tagslut/storage/v3/schema.py`, and `migration_runner.py`, then run a single isolated SQLite bootstrap/migrate probe only if static inspection does not settle it.[^1_2][^1_1]
- counterevidence considered: the presence of explicit v3 migration machinery suggests a convergence path exists, but that alone does not prove all supported bootstraps land in the same post-migration state.[^1_2]
- why it matters operationally: mixed bootstrap authority is a direct path to schema drift, feature flags appearing in one DB path but not another, and broken operator recovery instructions.[^1_2][^1_1]


### 7) Qobuz stale-credential behavior is still unresolved from local evidence

- severity: medium[^1_1][^1_2]
- status: open[^1_2][^1_1]
- exact file refs: `docs/OPERATOR_QUICK_START.md:16-18`, `tagslut/metadata/provider_state.py:143,155`, `tagslut/metadata/providers/qobuz.py:27,73`, `tagslut/metadata/auth.py:338`.[^1_1][^1_2]
- exact evidence: `docs/OPERATOR_QUICK_START.md` promises that `ts-auth` will tell the operator when the Qobuz session is expired and suggests a manual re-login command, but the actual provider-state and Qobuz code paths were not visible in the captured excerpts. That means explicit failure versus silent empty enrichment could not be confirmed or disproved from the available local output.[^1_2][^1_1]
- smallest repro or verification path: read `provider_state.py` and `providers/qobuz.py` at the cited spans, then run an import-only local status probe with nonexistent credentials and no network access if the code path still branches on runtime state.[^1_1][^1_2]
- counterevidence considered: the operator docs imply explicit signaling exists, but docs alone are not enough to settle provider failure behavior.[^1_2][^1_1]
- why it matters operationally: silent empty enrichment and explicit credential failure lead to very different operator responses and different false-confidence risks.[^1_1][^1_2]


## Contract map

- active/operator-facing: `docs/OPERATOR_QUICK_START.md` and `START_HERE.sh` are plainly operator-facing, and both present `ts-auth`, `ts-get`, and `ts-enrich` as the day-to-day commands. `tagslut get` and `tagslut fix` are also active live surfaces because the captured command code references blocked-cohort state and resume behavior directly.[^1_2][^1_1]
- compatibility-only: `tools/get --mp3` and `tools/get --dj` are explicitly described in `README.md` as routing into canonical `tagslut intake url`, `tools/get-sync` is explicitly deprecated, and `DJ_LIBRARY` is described as a compatibility alias to `MP3_LIBRARY`.[^1_2]
- legacy/dead: `docs/archive/` is explicitly marked historical by `AGENT.md`, `CLAUDE.md`, and `docs/README.md`. The wrapper-first docs also label the old 4-stage DJ pipeline and Rekordbox XML surface as legacy or archived, even though other docs contradict that claim.[^1_1][^1_2]
- ambiguous: plain `tools/get`, `tagslut intake url`, the DB-backed DJ/XML path, the actual on-disk location/definition of `ts-get`/`ts-enrich`/`ts-auth`, DB bootstrap authority, and Qobuz readiness signaling all remain ambiguous because the checked-in contract text conflicts and the captured code excerpts were incomplete for those exact implementation points.[^1_1][^1_2]


## Divergence table

| Surface | Claimed contract | Actual behavior | Status | Supporting refs |
| :-- | :-- | :-- | :-- | :-- |
| Wrapper story | `AGENT.md`, `CLAUDE.md`, and `OPERATOR_QUICK_START.md` say `ts-get`, `ts-enrich`, and `ts-auth` are the primary active wrappers. [^1_1][^1_2] | The docs clearly claim wrapper authority, but this audit did not capture the actual wrapper definitions or entrypoint location, so “real authoritative wrappers in practice, and where they live” is not locally settled. [^1_1][^1_2] | open [^1_1][^1_2] | `AGENT.md:6-15`, `CLAUDE.md:11-16`, `docs/OPERATOR_QUICK_START.md:13-18,31-38`, `START_HERE.sh:98-108`. [^1_1][^1_2] |
| Main intake entrypoint | `README.md` and `ARCHITECTURE.md` say `tools/get` is the primary or normal day-to-day intake path. [^1_1][^1_2] | `tagslut get` is the only locally confirmed cohort-aware path because it owns blocked-cohort lookup and `--fix`; `tools/get` remains operator-documented, so the repo’s current authority is split rather than singular. [^1_1][^1_2] | likely [^1_1][^1_2] | `README.md:81-108`, `docs/ARCHITECTURE.md:30-39`, `tagslut/cli/commands/get.py:15,296,328,335`, `tagslut/cli/commands/fix.py:280-318`, `_cohort_state.py:114,484`. [^1_1][^1_2] |
| `tools/get` vs `tagslut get` state | Wrapper docs imply one smooth umbrella flow. [^1_2] | The captured code shows cohort-state and blocked-cohort resume in `tagslut get`/`tagslut fix`, while the targeted grep found no corresponding `blocked_cohort` surface in `tools/get`; that makes lost resume/state semantics the most likely divergence. [^1_1][^1_2] | likely [^1_1][^1_2] | `tagslut/cli/commands/get.py`, `tagslut/cli/commands/fix.py`, `_cohort_state.py`, targeted grep over `tools/get`. [^1_1] |
| DJ/XML contract | `AGENT.md` and `CLAUDE.md` say DJ/XML is legacy/archive-only. [^1_1][^1_2] | `README.md` still calls the DB-backed DJ pipeline the “only supported workflow,” and `ARCHITECTURE.md` still labels the DB-backed DJ path canonical while also calling `tools/get --dj` compatibility-only. [^1_1][^1_2] | confirmed [^1_1][^1_2] | `AGENT.md:7-12`, `CLAUDE.md:11-13`, `README.md:110-164`, `docs/ARCHITECTURE.md:107-133`. [^1_1][^1_2] |
| Active docs index | `docs/README.md` says the active docs are exactly quick start, workflows, and architecture. [^1_2] | `README.md` still links and relies on several other non-archive docs such as `DJ_PIPELINE.md`, `DOWNLOAD_STRATEGY.md`, `BACKFILL_GUIDE.md`, and `PROVENANCE_INTEGRATION.md`, so the active-doc story is internally inconsistent. [^1_2] | confirmed [^1_2] | `docs/README.md:5-9`, `README.md:29-34,117,164`. [^1_2] |
| Self-audit signals | Repo scripts/tests should confirm structure and docs consistency. [^1_1] | The layout audit reports missing required files, the docs-consistency script crashes on a missing file, and the repo-structure test fails on a now-linkless `docs/README.md`. [^1_1] | confirmed [^1_1] | baseline outputs from `audit_repo_layout.py`, `check_cli_docs_consistency.py`, and `tests/test_repo_structure.py`. [^1_1] |
| Hardcoded paths | Operator docs/bootstraps imply a portable setup. [^1_1][^1_2] | The active quick-start and bootstrap surfaces still hardcode `/Users/georgeskhawam/Projects/tagslut` and `/Volumes/MUSIC/...`, which are live assumptions for the advertised workflow. [^1_1][^1_2] | confirmed [^1_1][^1_2] | `docs/OPERATOR_QUICK_START.md:6,25`, `START_HERE.sh:50-53,86-90`, `README.md:101-103`. [^1_1][^1_2] |
| DB bootstrap | Mixed schema files suggest a legacy-plus-v3 story. [^1_2] | The repo contains both legacy and v3 schema surfaces, but this audit did not capture enough code to prove whether all supported bootstrap paths converge. [^1_1][^1_2] | open [^1_1][^1_2] | `tagslut/storage/schema.py`, `tagslut/storage/v3/schema.py`, `migration_runner.py`, `0018_blocked_cohort_state.sql`, layout-audit output. [^1_1][^1_2] |
| Qobuz auth failure | Quick-start says expired Qobuz sessions are explicitly signaled by `ts-auth`. [^1_1] | The actual provider code path was not captured, so explicit failure versus silent empty enrichment remains unresolved. [^1_1][^1_2] | open [^1_1][^1_2] | `docs/OPERATOR_QUICK_START.md:16-18`, `provider_state.py`, `providers/qobuz.py`, `auth.py`. [^1_1][^1_2] |

## Open questions

- Where are `ts-get`, `ts-enrich`, and `ts-auth` actually defined, and are they shell functions, package entrypoints, or external wrappers? The docs/bootstrap story says they are authoritative, but this audit did not capture the implementation location.[^1_2][^1_1]
- Does plain `tools/get <url>` delegate into the same cohort-aware state model as `tagslut get`, or only the `--mp3`/`--dj` branches do that? That is the narrowest unresolved question behind the state-divergence finding.[^1_1][^1_2]
- Is the suspected local-path `tagslut get` unreachable retag/output block real at `get.py:123`, or is the hypothesis wrong once the missing span is read?[^1_1]
- Do the supported DB bootstrap paths converge to the same post-migration usable state, or does one path omit v3 migration coverage such as blocked-cohort state?[^1_2][^1_1]
- Do stale or missing Qobuz credentials raise an explicit readiness/error state, or can enrichment silently collapse to empty results?[^1_2][^1_1]


## Remediation order

1. Freeze one operator contract and remove the contradiction first: pick either wrapper-first/cohort-aware CLI or `tools/get`-first, then align `AGENT.md`, `CLAUDE.md`, `README.md`, `docs/README.md`, `docs/ARCHITECTURE.md`, and `docs/OPERATOR_QUICK_START.md` to that single story. This is the highest risk reducer because it controls every later operator decision.[^1_1][^1_2]
2. Make `tools/get` either fully delegate to the cohort-aware CLI path or explicitly demote it to compatibility-only in docs and operator bootstrap. That is the shortest path to eliminating likely state loss around blocked cohorts and resume flows.[^1_2][^1_1]
3. Repair the repo’s confidence layer immediately after the contract freeze: either restore `docs/OPERATIONS.md` and the expected migration helper, or update `audit_repo_layout.py`, `check_cli_docs_consistency.py`, and `tests/test_repo_structure.py` to the current documented surface. Right now the self-audit layer is already broken.[^1_1]
4. Remove or parameterize live absolute path assumptions in `START_HERE.sh` and active operator docs. This is lower risk than the contract split, but it is still a live portability and bootstrap correctness issue.[^1_2][^1_1]
5. Name one DB/bootstrap authority and test only that path. Until that is explicit, schema and migration drift will stay hard to reason about.[^1_1][^1_2]
6. Add one narrow local test for Qobuz stale-credential behavior and one narrow local test for local-path `tagslut get` behavior. Those are the cheapest unresolved operator-facing risks left after the contract and confidence layers are fixed.[^1_2][^1_1]

<div align="center">⁂</div>

[^1_1]: lets-continue-here-handle-the-hMN4_meyQAqY6_yGa_ls1A.md

