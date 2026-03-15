This handover describes the `tagslut` repository as seen in your local handoff bundle and is structured to be consumed by Codex (or any AGENT.md-aware coding agent) with an emphasis on safety, observability, and DJ‑pipeline workflows. It focuses on what can be established from the git state, repo inventory, and runtime snapshot you captured, and points Codex toward the right files and patterns rather than re‑stating documentation we cannot see directly.[1][2][3][4]

***

## Repository identity and branch state

The repository root is `/Users/georgeskhawam/Projects/tagslut`, with git reporting `HEAD` at commit `95614e55c4a2d9e36fd145db6b0962bc69b73b8c` on branch `dev` tracking `origin/dev` with no ahead/behind delta (`branch.ab +0 -0`). The current descriptive tag is `v3-baseline-2026-03-04-182-g95614e5`, which strongly suggests you are on a v3 baseline line with at least 182 commits since the tag base. Git status shows no modified tracked files and a small set of untracked files (two `collect_repo_context` scripts, three `handoff_bundle_repo_context_...` directories, and a `rekordbox_v2.xml` variant), indicating a clean working tree with only tooling and export artifacts untracked.[4][1]

The `00_MANIFEST.txt` reiterates that this is a “tagslut local handoff bundle” capped at 5 files and summarizes that there are 0 modified tracked files, 31 untracked files, 31 568 ignored files, 158 tool files, 165 test files, and 0 migration files as detected by its inventory logic. The absence of staged or unstaged diffs is confirmed in `04_LOCAL_CHANGES.patch`, whose sections for unstaged, staged, and full‑vs‑HEAD are present but contain no actual diff hunks. Collectively this means Codex can treat `origin/dev` plus local untracked context as the canonical code surface, without needing to account for hidden local modifications.[5][1][4]

***

## Documentation and agent configuration surface

The repo contains a top‑level `AGENT.md` of about 16 KB and a `CLAUDE.md`, strongly indicating that the project is explicitly configured for agentic coding tools that read structured agent configuration files. The presence of an AGENT.md aligns with the emerging ecosystem where agentic coding tools use a single, project‑local machine‑readable document to learn build commands, test strategy, coding conventions, and safety constraints, analogous to `AGENTS.md` and related formats. For Codex specifically, OpenAI’s guidance is to centralize instructions on autonomy level, tool usage, and persistence in such a file, and this project is following that pattern.[3][6][7][8][9][4]

There is a rich docs tree under `docs/` with files including `ARCHITECTURE.md`, `CORE_MODEL.md`, `DB_V3_SCHEMA.md`, `DJ_POOL.md`, `DJ_REVIEW_APP.md`, `DJ_WORKFLOW.md`, `OPERATIONS.md`, `PHASE1_STATUS.md`, `PHASE5_LEGACY_DECOMMISSION.md`, `PROGRESS_REPORT.md`, `PROJECT.md`, `SCRIPT_SURFACE.md`, `SURFACE_POLICY.md`, `TROUBLESHOOTING.md`, `WORKFLOWS.md`, and `ZONES.md`. An extensive `docs/archive/` subtree contains earlier handover and process documents such as `HANDOVER_2026-02-01.md`, `RESTRUCTURING_PLAN_2026.md`, `SCANNER_V1*.md`, `QUALITY_GATES.md`, and multiple workflow cheat‑sheets and legacy decommissioning plans, which Codex can mine for historical intent and invariants if asked to reason about design evolution instead of just current behavior. At the top level, `README.md`, `REPORT.md`, `CHANGELOG.md`, `SECURITY.md`, and `LICENSE` define project overview, status reporting, security posture, and licensing, and should be considered mandatory first‑reads for any Codex session that needs broad context rather than a narrow task.[3][4]

***

## High‑level domain and objectives

From filenames and artifacts, `tagslut` is clearly a DJ library curation and export system centered around a “v3” music database (`music_v3`) and integrated with DJ tools such as Rekordbox and external content sources like Beatport and Qobuz. Archived DJ playlists under `archive/dj_playlists_local/*.m3u8` (e.g. `bar_playlist`, `club_playlist`, `energy_*`, `safe_top1k`) show that the project manages curated sets of tracks for different gigs or energy profiles, which are then exported or transformed for performance environments. Config files such as `config/dj/dj_curation*.yaml`, `config/dj/crates/*.m3u8`, `config/policies/*.yaml`, `config/gig_overlay_rules.yaml`, and `config/zones.yaml.example` indicate that the system encodes DJ curation rules, crate definitions, safety policies, gig‑specific overlays, and physical or logical “zones” (likely library partitions or deployment targets) as structured configuration.[2][4][3]

Local runtime logs under `artifacts/compare/onetagger_*`, `artifacts/compare/post_move_enrich_art_*`, and `artifacts/dj_usb_incr_*` suggest workflows for integrating with OneTagger, performing post‑move enrichment (e.g. artwork, metadata), and incremental Rekordbox/USB exports, further supporting the view that `tagslut` orchestrates a chain from acquisition to curated, performance‑ready exports. The presence of `artifacts/audit/metadata_audit_*.csv` and JSON summaries indicates systematic metadata quality auditing, with numeric summaries and flag exports that Codex can consume to justify or validate changes to rules and schema. Combined with `docs/DJ_WORKFLOW.md`, `docs/DJ_POOL.md`, `docs/WORKFLOWS.md`, and `docsaudit/DJWORKFLOWAUDIT.md`, this gives Codex a well‑documented domain model that is strongly anchored in DJ practice rather than being a generic tagging library.[2][4][3]

***

## Core code structure and subsystems

From `git ls-files` and the repo inventory, the code is organized into several Python packages and CLI layers: `tagslutcore*`, `tagslutdj*`, `tagslutexec*`, `tagslutclicommands*`, `tagslutcli*`, `tagslutdecide*`, and a set of `scripts/*.py` one‑offs and operational tools. The `tagslutcore` modules (e.g. `tagslutcorehashing.py`, `tagslutcoreintegrity.py`, `tagslutcoremetadata.py`, `tagslutcorescanner.py`, `tagslutcorezoneassignment.py`) appear to implement low‑level primitives for hashing, integrity checks, metadata manipulation, scanning the filesystem, and assigning tracks to “zones”, and these should be treated as the foundational layer upon which higher abstractions build. The `tagslutdj` modules (e.g. `tagslutdjadmission.py`, `tagslutdjclassify.py`, `tagslutdjcuration.py`, `tagslutdjexport.py`, `tagslutdjgigprep.py`, `tagslutdjrekordboxprep.py`, `tagslutdjtranscode.py`, `tagslutdjxmlemit.py`) encapsulate DJ‑specific workflows like intake/admission, classification, curation rules, export, gig preparation, Rekordbox preparation, transcoding, and XML emission, and are likely to be the main touchpoints for Codex when evolving the DJ pipeline.[4][3]

The CLI layer is defined by `tagslutclicommands/*.py` and driver files like `tagslutclimain.py`, `tagslutcliinit.py`, and `tagslutcliscan.py`, which group commands into domains such as `auth`, `decide`, `dj`, `execute`, `export`, `gig`, `index`, `intake`, `library`, `mp3`, `ops`, `report`, `scan`, `tag`, and `verify`. A small `tagslutweb*` surface (`tagslutwebinit.py`, `tagslutwebreviewapp.py`) exists, indicating a web‑based review application, likely fronting the DJ review or promotion pipeline documented in `docs/DJ_REVIEW_APP.md`, but it appears secondary to the CLI as far as the current code layout reveals. Numerous `scripts/*.py` files (e.g. `scriptsdbcreatemusicv3db.py`, `scriptsdbmigratev2tov3.py`, `scriptsdjexportreadyv3.py`, `scriptsdjbuildpoolv3.py`, `scriptsgig0*`, `scriptslibraryexport.py`, `scriptsvalidatev3dualwriteparity.py`) implement migration, reporting, and one‑off operations; Codex should treat these as operational entrypoints and avoid refactoring them aggressively without cross‑checking `docs/SCRIPT_SURFACE.md` and `docs/OPERATIONS.md`.[3][4]

### Subsystem overview

| Subsystem family            | Representative files (by name)                                                                 | Likely responsibility (from naming and layering)                                                                 |
|----------------------------|-----------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| Core data & integrity      | `tagslutcorehashing.py`, `tagslutcoreintegrity.py`, `tagslutcoremetadata.py`, `tagslutcorescanner.py`, `tagslutcorezoneassignment.py`[4] | File hashing, integrity checks, metadata normalization, library scanning, and zone targeting primitives.        |
| DJ workflow & curation     | `tagslutdjadmission.py`, `tagslutdjclassify.py`, `tagslutdjcuration.py`, `tagslutdjexport.py`, `tagslutdjrekordboxprep.py`, `tagslutdjxmlemit.py`[4] | End‑to‑end DJ pipeline from intake/admission through classification, curation, export, and Rekordbox XML output. |
| Orchestration & execution  | `tagslutexeccanonicalwriteback.py`, `tagslutexeccompanions.py`, `tagslutdecideplanner.py`[4] | Execution engine for applying decisions, writing tags, and running orchestrated jobs.                            |
| CLI surface                | `tagslutclimain.py`, `tagslutclicommandsdj.py`, `tagslutclicommandsexecute.py`, `tagslutclicommandsgig.py`, `tagslutclicommandsverify.py`[4] | Command‑line interface grouping commands per responsibility and providing human‑facing entrypoints.              |
| Operational scripts        | `scriptsdbcreatemusicv3db.py`, `scriptsdbmigratev2tov3.py`, `scriptsgig0*.sh`, `scriptsdjexportreadyv3.py`, `scriptsvalidatev3dualwriteparity.py`[4] | Migrations, exports, gig orchestration, and verification routines run by humans or automation.                  |

Each of these subsystems is documented or at least referenced by the docs tree (architecture, workflows, script surface), so Codex should always pair code exploration with doc lookup via `/open` or equivalent tools rather than inferring behavior solely from function names.[7][4]

***

## Data stores and schema context

Your runtime snapshot shows multiple SQLite databases under `artifacts/`, notably `artifacts/db/music_v3.pre_comment_score_import_20260311_1.db`, `artifacts/db/music_v3.pre_playlist_tag_import_20260311_1.db`, and `artifacts/tmp/music_v2.db`, which strongly suggests an active v3 schema with transitional snapshots taken around comment score and playlist tag imports. There is also `artifacts/beets_library.db`, implying that `tagslut` interoperates or at least borrows from a Beets music library as a reference or upstream canonical store. The existence of `docs/DB_V3_SCHEMA.md` and `data/checkpoints/reconcile_schema_0010.json` indicates that the v3 schema is formally documented and that reconciliation checkpoints exist to track schema alignment or migration status, which Codex must consult before making any DB‑touching change.[2][4][3]

Given the reported absence of migration files in the manifest summary (0 “migration files” detected), it is likely that v2→v3 migrations are handled via bespoke scripts like `scriptsdbmigratev2tov3.py` and `scriptsdbmigrationreportv2tov3.py` rather than ORM‑style migration frameworks, so Codex should avoid introducing a new migration system without coordinating with those scripts and the existing schema docs. The numerous `artifacts/backfill_v3_checkpoint_*.json` files represent long‑running backfill jobs segmented by row ranges (e.g. 500, 1000, 1500, up to 27 500+ IDs), and their size growth over ranges implies they store progress metadata and possibly error statistics that should be preserved during any schema or backfill logic refactor.[1][4][3]

***

## Runtime environment and tooling

The system snapshot shows `Python 3.14.2` as the active interpreter, `pip 25.3`, `Poetry 2.3.1`, and `uv 0.9.28` installed via Homebrew, with a local `.venv` present, indicating a modern, fairly bleeding‑edge Python toolchain. Project lock and config files include `pyproject.toml`, `poetry.lock`, and `uv.lock` both at the repo root and inside the handoff bundles’ `40_python` directories, so dependency resolution relies on these, and Codex should never modify them without respecting the existing dependency manager choice and lock semantics. Environment configuration is captured in `.env` and `.env.example` at the root and mirrored inside the handoff bundle `90_local_runtime` subdirectories, which act as anonymized or partially‑scrubbed snapshots of local environment config for the handover.[1][2]

The runtime snapshot also enumerates a dense set of Python packages cached under `.venv` and tool caches for pytest (`.pytest_cache`), mypy (`.mypy_cache`), ruff (`.ruff_cache`), and others, implying an established testing and linting stack that Codex should respect by running or at least keeping tests and linters green when changing code. Coverage data is present as `.coverage`, and baseline artifact files like `artifacts/flake8_baseline_2026-03-08.txt`, `artifacts/mypy_baseline_2026-03-08.txt`, and `artifacts/test_baseline_2026-03-08.txt` further codify the expected lint/test status at a specific cut‑off, which is useful for Codex to compare against if asked to “return to a clean baseline”. Makefile and top‑level tooling files exist (`Makefile`, `.flake8`), so build and lint commands are likely documented there and in AGENT.md, in line with best practice for agent configuration where build, test, and lint commands are explicitly listed for tools to call.[6][8][4][2][3]

***

## Operational workflows and artifacts

The repo contains CI configuration under `.github/workflows/ci.yml`, `claude.yml`, and `claude-code-review.yml`, and a `.github/prompts/` directory with prompts like `dj-pipeline-hardening.prompt.md`, `dj-workflow-audit.prompt.md`, `lexicon-reconcile.prompt.md`, and `open-streams-post-0010.prompt.md`, demonstrating that past work has already codified agent prompts for DJ‑pipeline hardening, workflow auditing, and lexicon reconciliation. These prompt files are valuable reference for Codex: they encode the mental model and constraints previous agent runs were expected to follow, and Codex can reuse or adapt those patterns when asked to perform similar audits or transformations.[4][3]

Operational logs under `artifacts/` are richly segmented: 
- `artifacts/compare/*` covers comparisons for OneTagger runs, Beatport download lists, post‑move enrichments, and reprocessing actions (e.g. quarantine metadata dupes), 
- `artifacts/tmp/enrich_*.log` shows transient enrichment runs, 
- `artifacts/v3.0.0/*` records v3‑specific experiments like `dj_review_rehearsal.log` and `quarantine_promote_dryrun_after_duration_fix.log`.[2][3]
There are also high‑value reports like `artifacts/_work_isrc_dupe_report*.md`, `artifacts/aiff_*` CSV/TXT pairs for AIFF quality and bitdepth analysis, and `artifacts/audit/metadata_audit_*` files which collectively form a detailed audit trail of audio quality, duplicates, and metadata anomalies, and these should be preserved as historical evidence rather than casually deleted in cleanup refactors.[3]

***

## Codex‑specific guidance and usage patterns

OpenAI’s Codex prompting guidance emphasizes that the agent should receive: (1) a strong project‑specific system prompt, (2) a small set of key files (AGENT, README, architecture docs), and (3) tools for reading and editing files, then be allowed to run in a loop until the task is done. In this repo, AGENT.md, README.md, REPORT.md, docs/ARCHITECTURE.md, docs/WORKFLOWS.md, docs/DJ_WORKFLOW.md, and docs/SURFACE_POLICY.md collectively form the “small set of key files” that Codex should load first when asked to work at architectural or DJ‑workflow level, while more specialized tasks (e.g. DB migration, gig prep) should add DB schema and script docs to the initial context. Codex should be configured to treat `tagslutclimain.py` and the `tagslutclicommands/` submodules as the primary execution surface, issuing changes that keep CLI contracts backward‑compatible unless an explicit versioned deprecation plan is documented in `CHANGELOG.md` or `docs/PROGRESS_REPORT.md`.[6][7][4][3]

Because this project is running on a local machine with real DJ libraries and artifact databases (including Beets and `music_v3` snapshots), agents must be instructed in AGENT.md (and re‑emphasized in prompts) to avoid destructive operations on `artifacts/` and `archive/` directories except when explicitly authorized, treating them as append‑only logs and historical state. Any Codex session that proposes schema or migration changes should be forced to (a) read `docs/DB_V3_SCHEMA.md` and `scriptsdb*` files first, (b) produce explicit migration plans and backout procedures in Markdown, and (c) keep new scripts consistent with existing naming conventions and script surface policies described in `docs/SCRIPT_SURFACE.md` and `docs/OPERATIONS.md`. In line with Codex best practices, large‑scale edits should be performed via patch tools (e.g. `apply_patch`) with small, auditable diffs, rather than wholesale rewrites of multi‑hundred‑line files in a single step.[7][4][2][3]

***

## Perplexity collections and Codex research loop

Although we cannot inspect your specific Perplexity collection, Perplexity “Collections” are designed to group related threads, preserve research context, and expose it as a reusable space with custom AI instructions. Your `tagslut` collection likely contains prior analyses of DJ workflows, prompts for auditing, and Codex interactions, so a robust Codex workflow is: query the Perplexity collection for background (e.g. “summarize current DJ pipeline constraints”), then use Codex for code‑level execution guided by that summary. With the Composio‑based integration between Codex and Perplexity MCP, it is possible to let Codex call Perplexity for up‑to‑date research from within the coding session, but any such behavior should still be constrained by the local AGENT.md rules and by the requirement to treat `docs/` and config files as the source of truth for business logic.[10][11][12][13][6]

Perplexity Collections also support collaborative sharing and topic‑scoped instructions, which means your `tagslut` space can encode higher‑level DJ goals (“prioritize club‑ready energetic tracks”, “avoid borderline artists from `config/blocklists`”) that Codex can regard as non‑code‑level invariants when modifying rules or pipelines. In other words, Perplexity encodes the “why” of your DJ system, while Codex operates on the “how” in this repo; this handover report and AGENT.md connect those two layers.[11][12][13][6][3]

***

## Risks, invariants, and quality gates

The presence of archived docs like `docs/archive/QUALITY_GATES.md`, `docs/archive/PROVENANCE_AND_RECOVERY.md`, `docs/archive/SURFACE_POLICY.md`, and decommissioning reports for legacy v2 workflows signals that the project has explicit quality gates and provenance requirements that must not be bypassed in pursuit of quick fixes. Likewise, `config/policies/*.yaml` (e.g. `bulk_recovery.yaml`, `dj_strict.yaml`, `library_balanced.yaml`) encode policy profiles that almost certainly represent user‑facing commitments around safety (e.g. which tracks make it into performance crates), and Codex should treat those as invariants that can be refined but not silently broken. When in doubt, Codex should read the relevant policy and quality docs and then propose changes via a Markdown design note checked into `docs/` or `docs/archive/` rather than directly implementing behavior changes in code or config.[7][4][3]

Audit artifacts like `metadata_audit_*` and `_work_isrc_dupe_*` reports, along with v3.0.0 rehearsal logs, show that significant manual effort has gone into validating metadata integrity and de‑duplication; agents must not undo or invalidate that work without a similarly rigorous re‑audit plan. Finally, backfill checkpoints and decommission logs for older tools (e.g. `docs/archive/decommission-2026-02-15/legacy-tools/...`) capture previous system boundaries; Codex should respect the fact that certain old tools are intentionally retired and avoid re‑introducing dependencies on them, instead using v3 primitives and documented workflows.[4][3]

***

## Open work and phase tracking

`docs/PHASE1_STATUS.md`, `docs/PHASE5_LEGACY_DECOMMISSION.md`, `docs/PROGRESS_REPORT.md`, `docs/REDESIGN_TRACKER.md`, and numerous archived phase specs under `docs/archive/phase-specs-2026-02-09/*.md` document a multi‑phase migration and redesign program that has already retired legacy systems by February 2026. The existence of both current and archived `PHASE5_LEGACY_DECOMMISSION` docs indicates that a major legacy decommission has been completed and then re‑documented or refined, which Codex should treat as frozen history rather than a moving target unless progress reports state otherwise. Any request to Codex to “continue” or “update” a phase plan should start from the latest non‑archived docs in `docs/` and only consult the archived specs to understand why certain decisions were made, not to resurrect superseded approaches.[4]

The `docs/archive/repo-audit-report-draft-2026-03-09.md` and `docsaudit/*` files (e.g. `DJWORKFLOWAUDIT.md`, `DJWORKFLOWTRACE.md`, `MISSING_TESTS.md`, `REKORDBOX_XML_INTEGRATION.md`) capture fairly recent audits and gaps, providing Codex with a shopping list of known weaknesses (e.g. missing tests, workflow edge cases) that can be turned into concrete coding tasks. This means that a Codex session aimed at “hardening” or “closing gaps” should not invent goals but instead read these audit docs, extract open items into an issue‑like list, and then implement them in small, verifiable steps with corresponding updates to test and doc surfaces.[7][4]

***

## Annex A – Key files and docs for Codex bootstrapping

For any non‑trivial Codex session, you should seed Codex with these files as initial context (by explicit path, not by search): 

- `AGENT.md` – global agent configuration and project rules for all coding agents.[3]
- `README.md`, `REPORT.md` – project overview and recent status.[3]
- `docs/ARCHITECTURE.md` – overall architecture, layers, and dependencies.[4]
- `docs/WORKFLOWS.md`, `docs/DJ_WORKFLOW.md`, `docs/DJ_POOL.md` – detailed workflow descriptions and DJ‑specific behavior.[4]
- `docs/DB_V3_SCHEMA.md`, `data/checkpoints/reconcile_schema_0010.json` – schema definitions and reconciliation checkpoints.[3][4]
- `docs/SURFACE_POLICY.md`, `docs/SCRIPT_SURFACE.md`, `docs/OPERATIONS.md` – which scripts and commands are “supported surfaces” and how they should be used.[4]
- `.github/prompts/*` – prior AI/agent prompts for DJ pipeline and lexicon work.[3]

This set should be considered the minimal “Codex bootstrap pack”; additional domain‑specific docs can be added case‑by‑case (e.g. gig planning docs for gig‑related tasks, audit docs for audit‑related improvements).[4]

***

## Annex B – Local environment and data footprint snapshot

The local machine is a macOS host (`mac.local`) running Python 3.14 via Homebrew, with a project‑local virtual environment under `.venv` and standard Python tooling (pip, Poetry, uv) installed. The repo root contains `.env` and `.env.example`, and the handoff bundle includes copies of these in `90_local_runtime/`, which may have had sensitive values scrubbed but retain enough structure for Codex to understand environment variable names and schema.[1][2]

Data footprint includes:
- `artifacts/beets_library.db` – external Beets library integration.[2]
- `artifacts/db/music_v3.*.db` – v3 music database snapshots around specific backfill steps.[2]
- `artifacts/tmp/music_v2.db` – legacy v2 database still present for reference or migration.[2]
- Extensive `.log` files in `artifacts/` for compare, tmp, v3.0.0, and other workflows, plus caches and coverage artifacts as noted earlier.[2][3]

Codex should treat all of these as immutable observational data in the context of code changes, unless explicitly tasked with data migration or cleanup and instructed to operate on copies or well‑defined subsets.[2][4]

***

## Annex C – Codex prompting patterns and safety rails

Per OpenAI’s Codex documentation, high‑quality prompts for coding agents should: (1) clearly define the task, (2) specify constraints (tests must pass, architecture must be respected), (3) enumerate available tools (e.g. file read/edit, terminal, Perplexity MCP), and (4) require stepwise planning and verification. In this project, those constraints should explicitly mention: do not mutate `artifacts/` or `archive/` by default, preserve DB invariants as defined in `docs/DB_V3_SCHEMA.md`, and always run or at least consider running the relevant tests and lint commands when touching core modules or CLI surfaces.[6][7][3][4]

AGENT.md should be updated (if not already) to describe the expected Codex autonomy level (e.g. “autonomously apply patches but do not run external scripts without confirmation”), to list canonical commands to run tests and lint, and to encode preferences around coding style, logging, and error handling, in line with AGENT.md/AGENTS.md best practices. Additionally, when integrating Perplexity MCP as described by Composio, prompts should insist that Codex treat Perplexity answers as advisory, deferring to local docs and config files where conflicts arise.[8][14][10][6][3]

***

## Annex D – Glossary (project‑specific, from structure)

- **Zone** – A logical or physical library segment; see `tagslutcorezoneassignment.py` and `docs/ZONES.md` for definitions and mappings (zones likely correspond to different storage locations or performance contexts).[4]
- **DJ pool** – The curated subset of the library eligible for gigs; implemented via `tagslutdj*` modules and documented in `docs/DJ_POOL.md`.[4]
- **Backfill** – Long‑running jobs that populate or fix v3 database fields from older data; see `artifacts/backfill_v3_checkpoint_*.json` and scripts like `scriptsdb*`.[3][4]
- **Script surface** – The set of scripts and entrypoints considered supported for human or CI use, enumerated in `docs/SCRIPT_SURFACE.md` and reflected in `scripts/*.py`.[4]
- **Quality gates** – Documented checks on metadata, duplicates, and audio quality defined in `docs/archive/QUALITY_GATES.md` and implemented via audit scripts and artifacts.[3][4]

This glossary should be extended over time by reading the actual docs and capturing any additional domain‑specific terms (e.g. lexicon, quarantine, companion files) so that Codex and Perplexity operate with a shared, explicit vocabulary rather than relying solely on file naming conventions.[12][4]

Sources
[1] 00_MANIFEST.txt https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/43550134/33745923-5589-497a-a633-1e4f0ddaa346/00_MANIFEST.txt?AWSAccessKeyId=ASIA2F3EMEYE4UACOLMT&Signature=INy1FNtbpn6O4okQ3IRe5E4Z7tg%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEPD%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJGMEQCIGTcgpX6wNkUynnsiVAsk9lTS%2Fc%2BhlGKDJduKw7%2BISMGAiBJLj1rlTPIYLT4AwS3d9EDiED5PxJRLivalSLEXrN2yCr8BAi4%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMjG2X0nBRGPZIxMNYKtAElWZ%2FYIvcet2ge%2BGVIT8G8JFBD18pBR%2B1dRn2RGdYWRiYVWsDJ8iSGxOOKkPEjT4FhBtGD1dAI2Ij6d4h20M1GpbJ6nP3y5Py3QzbZn9B3K8VhyIGTq06fOEGCN3rrJq8S%2Bjrj549%2BwGqDmmrgkbzBH63TF8Ee0ltavBhpOOqpjtTPymzL4L7UDrlnfAB190Q%2Bg%2BdEmcB2bv8zLGf8qfZ46%2BWZNslFVqSK9WxRCYLhYtxCf19lo2uDWVDIgQ3rY3mrX1YXehXmR%2B9j2NwQJmHiPXTUs79anZJ22VJaZ0GM564Z3omYu%2BhhFH%2B9khHT44WB65BgDMSm4lZqJZKZH8UDvpnm6J6p1rNem8PKC175l8Z1H7KJXXDGcb06gON2YwTBpJPbmvBOwDSlWELPsr04pSX%2Bh3MSp8aRCm5t0NSrF%2BvI1vF308S%2ByVakrESPT%2F6CxSjtpR2fqMIfr3zRGt55dhovCETzdYEfoQsID80VQqPE4BydydwsR3Zqx6p4ePe0U3qMVNnn4CvGieSXwG%2FgILQk2JY7kjOw2z0Myd5Cl1DPorwPGfIRoEry%2B2VS3LQAKIqige5Ocv%2Bm%2B7sWwGpSgV4SU8912Iz2GygW9WjYO9T0I0O7At1%2BlfvZNfXdAh6kKzm2vhYN%2FpoBLodyKCIM7nafzEghSBtBE%2FMNRGkTQQesWIcaQg0ZcDaNF7N8xb8EamQgJJnl06mRrP542lGXWGGC9JJxSrfQ1VvbrWQTg2lsvqkKvIsjD6%2BryAUv74XvbmnE9B7HN5a70iQjT4a2zDitdnNBjqZATSUpIBRsV1UaU8P%2FsfpOvWyCznDC7MMO92e0R%2F%2F8w%2BH17fG2XnKVJmwsob5AepdnA%2F7opGTHpqE0CjMKBB0%2F4m%2BKqGOJTRTv%2B0%2B3%2FFNHSPL2CmY4uf2o2xGzuirTB0YcjSA8rWwLfNfJfFOylu7KRasRy8DdVbp4uEX3dkrt3rjg2jMxC3XyMs%2FfpjO6LoqKeF3hWNEWIIjrQ%3D%3D&Expires=1773560785
[2] 03_LOCAL_RUNTIME.txt https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/43550134/4b305544-d354-4699-946f-981ccead24a5/03_LOCAL_RUNTIME.txt?AWSAccessKeyId=ASIA2F3EMEYE4UACOLMT&Signature=WNmy2yGPc2VT7sGCYURblNnKgNg%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEPD%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJGMEQCIGTcgpX6wNkUynnsiVAsk9lTS%2Fc%2BhlGKDJduKw7%2BISMGAiBJLj1rlTPIYLT4AwS3d9EDiED5PxJRLivalSLEXrN2yCr8BAi4%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMjG2X0nBRGPZIxMNYKtAElWZ%2FYIvcet2ge%2BGVIT8G8JFBD18pBR%2B1dRn2RGdYWRiYVWsDJ8iSGxOOKkPEjT4FhBtGD1dAI2Ij6d4h20M1GpbJ6nP3y5Py3QzbZn9B3K8VhyIGTq06fOEGCN3rrJq8S%2Bjrj549%2BwGqDmmrgkbzBH63TF8Ee0ltavBhpOOqpjtTPymzL4L7UDrlnfAB190Q%2Bg%2BdEmcB2bv8zLGf8qfZ46%2BWZNslFVqSK9WxRCYLhYtxCf19lo2uDWVDIgQ3rY3mrX1YXehXmR%2B9j2NwQJmHiPXTUs79anZJ22VJaZ0GM564Z3omYu%2BhhFH%2B9khHT44WB65BgDMSm4lZqJZKZH8UDvpnm6J6p1rNem8PKC175l8Z1H7KJXXDGcb06gON2YwTBpJPbmvBOwDSlWELPsr04pSX%2Bh3MSp8aRCm5t0NSrF%2BvI1vF308S%2ByVakrESPT%2F6CxSjtpR2fqMIfr3zRGt55dhovCETzdYEfoQsID80VQqPE4BydydwsR3Zqx6p4ePe0U3qMVNnn4CvGieSXwG%2FgILQk2JY7kjOw2z0Myd5Cl1DPorwPGfIRoEry%2B2VS3LQAKIqige5Ocv%2Bm%2B7sWwGpSgV4SU8912Iz2GygW9WjYO9T0I0O7At1%2BlfvZNfXdAh6kKzm2vhYN%2FpoBLodyKCIM7nafzEghSBtBE%2FMNRGkTQQesWIcaQg0ZcDaNF7N8xb8EamQgJJnl06mRrP542lGXWGGC9JJxSrfQ1VvbrWQTg2lsvqkKvIsjD6%2BryAUv74XvbmnE9B7HN5a70iQjT4a2zDitdnNBjqZATSUpIBRsV1UaU8P%2FsfpOvWyCznDC7MMO92e0R%2F%2F8w%2BH17fG2XnKVJmwsob5AepdnA%2F7opGTHpqE0CjMKBB0%2F4m%2BKqGOJTRTv%2B0%2B3%2FFNHSPL2CmY4uf2o2xGzuirTB0YcjSA8rWwLfNfJfFOylu7KRasRy8DdVbp4uEX3dkrt3rjg2jMxC3XyMs%2FfpjO6LoqKeF3hWNEWIIjrQ%3D%3D&Expires=1773560785
[3] 02_REPO_INVENTORY.tsv https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/43550134/0948f92d-3807-415a-8ae7-9cb997c82c4a/02_REPO_INVENTORY.tsv?AWSAccessKeyId=ASIA2F3EMEYE4UACOLMT&Signature=IdS%2FmcOLZu0jp68D4DL9sJEGJHo%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEPD%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJGMEQCIGTcgpX6wNkUynnsiVAsk9lTS%2Fc%2BhlGKDJduKw7%2BISMGAiBJLj1rlTPIYLT4AwS3d9EDiED5PxJRLivalSLEXrN2yCr8BAi4%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMjG2X0nBRGPZIxMNYKtAElWZ%2FYIvcet2ge%2BGVIT8G8JFBD18pBR%2B1dRn2RGdYWRiYVWsDJ8iSGxOOKkPEjT4FhBtGD1dAI2Ij6d4h20M1GpbJ6nP3y5Py3QzbZn9B3K8VhyIGTq06fOEGCN3rrJq8S%2Bjrj549%2BwGqDmmrgkbzBH63TF8Ee0ltavBhpOOqpjtTPymzL4L7UDrlnfAB190Q%2Bg%2BdEmcB2bv8zLGf8qfZ46%2BWZNslFVqSK9WxRCYLhYtxCf19lo2uDWVDIgQ3rY3mrX1YXehXmR%2B9j2NwQJmHiPXTUs79anZJ22VJaZ0GM564Z3omYu%2BhhFH%2B9khHT44WB65BgDMSm4lZqJZKZH8UDvpnm6J6p1rNem8PKC175l8Z1H7KJXXDGcb06gON2YwTBpJPbmvBOwDSlWELPsr04pSX%2Bh3MSp8aRCm5t0NSrF%2BvI1vF308S%2ByVakrESPT%2F6CxSjtpR2fqMIfr3zRGt55dhovCETzdYEfoQsID80VQqPE4BydydwsR3Zqx6p4ePe0U3qMVNnn4CvGieSXwG%2FgILQk2JY7kjOw2z0Myd5Cl1DPorwPGfIRoEry%2B2VS3LQAKIqige5Ocv%2Bm%2B7sWwGpSgV4SU8912Iz2GygW9WjYO9T0I0O7At1%2BlfvZNfXdAh6kKzm2vhYN%2FpoBLodyKCIM7nafzEghSBtBE%2FMNRGkTQQesWIcaQg0ZcDaNF7N8xb8EamQgJJnl06mRrP542lGXWGGC9JJxSrfQ1VvbrWQTg2lsvqkKvIsjD6%2BryAUv74XvbmnE9B7HN5a70iQjT4a2zDitdnNBjqZATSUpIBRsV1UaU8P%2FsfpOvWyCznDC7MMO92e0R%2F%2F8w%2BH17fG2XnKVJmwsob5AepdnA%2F7opGTHpqE0CjMKBB0%2F4m%2BKqGOJTRTv%2B0%2B3%2FFNHSPL2CmY4uf2o2xGzuirTB0YcjSA8rWwLfNfJfFOylu7KRasRy8DdVbp4uEX3dkrt3rjg2jMxC3XyMs%2FfpjO6LoqKeF3hWNEWIIjrQ%3D%3D&Expires=1773560785
[4] 01_GIT_STATE.txt https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/43550134/1cfd6abb-5dfa-4cbe-82c4-bb5641508146/01_GIT_STATE.txt?AWSAccessKeyId=ASIA2F3EMEYE4UACOLMT&Signature=%2FkndKKDwrh3zJv%2Bk0i3zPbfx%2FbY%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEPD%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJGMEQCIGTcgpX6wNkUynnsiVAsk9lTS%2Fc%2BhlGKDJduKw7%2BISMGAiBJLj1rlTPIYLT4AwS3d9EDiED5PxJRLivalSLEXrN2yCr8BAi4%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMjG2X0nBRGPZIxMNYKtAElWZ%2FYIvcet2ge%2BGVIT8G8JFBD18pBR%2B1dRn2RGdYWRiYVWsDJ8iSGxOOKkPEjT4FhBtGD1dAI2Ij6d4h20M1GpbJ6nP3y5Py3QzbZn9B3K8VhyIGTq06fOEGCN3rrJq8S%2Bjrj549%2BwGqDmmrgkbzBH63TF8Ee0ltavBhpOOqpjtTPymzL4L7UDrlnfAB190Q%2Bg%2BdEmcB2bv8zLGf8qfZ46%2BWZNslFVqSK9WxRCYLhYtxCf19lo2uDWVDIgQ3rY3mrX1YXehXmR%2B9j2NwQJmHiPXTUs79anZJ22VJaZ0GM564Z3omYu%2BhhFH%2B9khHT44WB65BgDMSm4lZqJZKZH8UDvpnm6J6p1rNem8PKC175l8Z1H7KJXXDGcb06gON2YwTBpJPbmvBOwDSlWELPsr04pSX%2Bh3MSp8aRCm5t0NSrF%2BvI1vF308S%2ByVakrESPT%2F6CxSjtpR2fqMIfr3zRGt55dhovCETzdYEfoQsID80VQqPE4BydydwsR3Zqx6p4ePe0U3qMVNnn4CvGieSXwG%2FgILQk2JY7kjOw2z0Myd5Cl1DPorwPGfIRoEry%2B2VS3LQAKIqige5Ocv%2Bm%2B7sWwGpSgV4SU8912Iz2GygW9WjYO9T0I0O7At1%2BlfvZNfXdAh6kKzm2vhYN%2FpoBLodyKCIM7nafzEghSBtBE%2FMNRGkTQQesWIcaQg0ZcDaNF7N8xb8EamQgJJnl06mRrP542lGXWGGC9JJxSrfQ1VvbrWQTg2lsvqkKvIsjD6%2BryAUv74XvbmnE9B7HN5a70iQjT4a2zDitdnNBjqZATSUpIBRsV1UaU8P%2FsfpOvWyCznDC7MMO92e0R%2F%2F8w%2BH17fG2XnKVJmwsob5AepdnA%2F7opGTHpqE0CjMKBB0%2F4m%2BKqGOJTRTv%2B0%2B3%2FFNHSPL2CmY4uf2o2xGzuirTB0YcjSA8rWwLfNfJfFOylu7KRasRy8DdVbp4uEX3dkrt3rjg2jMxC3XyMs%2FfpjO6LoqKeF3hWNEWIIjrQ%3D%3D&Expires=1773560785
[5] 04_LOCAL_CHANGES.patch https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/43550134/c67ddfd3-327d-4b3d-bde4-b260c37ef701/04_LOCAL_CHANGES.patch?AWSAccessKeyId=ASIA2F3EMEYE4UACOLMT&Signature=P4dvA9LrsOJK42xP0C9KoQ7cH%2F0%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEPD%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJGMEQCIGTcgpX6wNkUynnsiVAsk9lTS%2Fc%2BhlGKDJduKw7%2BISMGAiBJLj1rlTPIYLT4AwS3d9EDiED5PxJRLivalSLEXrN2yCr8BAi4%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAEaDDY5OTc1MzMwOTcwNSIMjG2X0nBRGPZIxMNYKtAElWZ%2FYIvcet2ge%2BGVIT8G8JFBD18pBR%2B1dRn2RGdYWRiYVWsDJ8iSGxOOKkPEjT4FhBtGD1dAI2Ij6d4h20M1GpbJ6nP3y5Py3QzbZn9B3K8VhyIGTq06fOEGCN3rrJq8S%2Bjrj549%2BwGqDmmrgkbzBH63TF8Ee0ltavBhpOOqpjtTPymzL4L7UDrlnfAB190Q%2Bg%2BdEmcB2bv8zLGf8qfZ46%2BWZNslFVqSK9WxRCYLhYtxCf19lo2uDWVDIgQ3rY3mrX1YXehXmR%2B9j2NwQJmHiPXTUs79anZJ22VJaZ0GM564Z3omYu%2BhhFH%2B9khHT44WB65BgDMSm4lZqJZKZH8UDvpnm6J6p1rNem8PKC175l8Z1H7KJXXDGcb06gON2YwTBpJPbmvBOwDSlWELPsr04pSX%2Bh3MSp8aRCm5t0NSrF%2BvI1vF308S%2ByVakrESPT%2F6CxSjtpR2fqMIfr3zRGt55dhovCETzdYEfoQsID80VQqPE4BydydwsR3Zqx6p4ePe0U3qMVNnn4CvGieSXwG%2FgILQk2JY7kjOw2z0Myd5Cl1DPorwPGfIRoEry%2B2VS3LQAKIqige5Ocv%2Bm%2B7sWwGpSgV4SU8912Iz2GygW9WjYO9T0I0O7At1%2BlfvZNfXdAh6kKzm2vhYN%2FpoBLodyKCIM7nafzEghSBtBE%2FMNRGkTQQesWIcaQg0ZcDaNF7N8xb8EamQgJJnl06mRrP542lGXWGGC9JJxSrfQ1VvbrWQTg2lsvqkKvIsjD6%2BryAUv74XvbmnE9B7HN5a70iQjT4a2zDitdnNBjqZATSUpIBRsV1UaU8P%2FsfpOvWyCznDC7MMO92e0R%2F%2F8w%2BH17fG2XnKVJmwsob5AepdnA%2F7opGTHpqE0CjMKBB0%2F4m%2BKqGOJTRTv%2B0%2B3%2FFNHSPL2CmY4uf2o2xGzuirTB0YcjSA8rWwLfNfJfFOylu7KRasRy8DdVbp4uEX3dkrt3rjg2jMxC3XyMs%2FfpjO6LoqKeF3hWNEWIIjrQ%3D%3D&Expires=1773560785
[6] Prompting https://developers.openai.com/codex/prompting/
[7] Codex Prompting Guide - OpenAI for developers https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide/
[8] AGENT.md: The Universal Agent Configuration File https://github.com/agentmd/agent.md
[9] AGENTS.md https://agents.md
[10] How to integrate Perplexityai MCP with Codex - Composio https://composio.dev/toolkits/perplexityai/framework/codex
[11] How to Use Perplexity Collections - LiveDemo https://livedemo.ai/tutorials/how-to-use-perplexity-collections/
[12] Perplexity AI: A Guide for Beginners https://www.jeffsu.org/perplexity-a-comprehensive-guide/
[13] Was sind Perplexity Collections? Und wie funktionieren sie? - Lilys AI https://lilys.ai/de/notes/how-to-use-perplexity-20251109/perplexity-collections-explained
[14] How to write a great agents.md: Lessons from over 2500 ... https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/
[15] タグを表示する https://docs.github.com/ja/desktop/managing-commits/managing-tags-in-github-desktop
[16] GitHub - delorenj/prompt-and-tag: Prompt-and-Tag is a tool designed to enhance AI-assisted development by seamlessly integrating your codebase with Large Language Models (LLMs). It creates synchronized snapshots of your code, making it easier to maintain context in AI conversations. https://github.com/delorenj/prompt-and-tag
[17] Question: "Some diagram description contains errors" · Issue #71 · skuro/plantuml-mode https://github.com/skuro/plantuml-mode/issues/71
[18] Code Samples For ``create A... https://docs.github.com/en/rest/git/tags
[19] codex/codex-rs/core/prompt.md at main · openai/codex · GitHub https://github.com/openai/codex/blob/main/codex-rs/core/prompt.md
[20] perplexipy/perplexipy/codex.py at master · CIME-Software/perplexipy https://github.com/CIME-Software/perplexipy/blob/master/perplexipy/codex.py
[21] Auto tag · Actions · GitHub Marketplace https://github.com/marketplace/actions/auto-tag
[22] Look for custom prompts in {project root}/.codex ... https://github.com/openai/codex/issues/4734
[23] Provide a SHA256 hash of file content · Issue #4195 · mozilla/pdf.js https://github.com/mozilla/pdf.js/issues/4195
[24] Build software better, together https://github.com/topics/tag
[25] OpenAI Codex CLI Settings and Custom Prompts https://github.com/feiskyer/codex-settings
[26] After installing Laravel version 11, I encountered an error ... https://github.com/laravel/framework/issues/50484
[27] Listing tags · cli cli · Discussion #8378 https://github.com/cli/cli/discussions/8378
[28] Example Prompt for Codex /answers https://gist.github.com/harish-garg/e24cf827d82215578729a513ab892695
[29] cv2.findEssentialMat() Error with 2 cameraMatrix · Issue #960 · opencv/opencv-python https://github.com/opencv/opencv-python/issues/960
[30] GitHub - TagStudioDev/TagStudio: A User-Focused Photo & File Management System https://github.com/TagStudioDev/TagStudio
[31] How to Use Prompt Engineering with Codex for Code Generation and Synthesis https://www.linkedin.com/pulse/how-use-prompt-engineering-codex-code-generation-jayrald-ado-
[32] Installation - TagStudio https://docs.tagstud.io/install/
[33] Codex replacement using Perplexity AI https://www.reddit.com/r/indotech/comments/1oh3w26/codex_replacement_using_perplexity_ai/
[34] TagStudio: A User-Focused Photo & File Management System https://docs.tagstud.io
[35] TagLib | TagLib https://taglib.org
[36] Making and Using a Codex Template Library - AI Prompting - Novelcrafter Live https://www.youtube.com/watch?v=Ws68qqOeCTQ
[37] Releases · Martchus/tageditor https://github.com/Martchus/tageditor/releases
[38] prompt - Open AI Codex examples - Google Sites https://sites.google.com/view/openaicodexexamples/escaperoom/next-level/prompt?authuser=2
[39] GitHub - mik3y/usb-serial-for-android: Android USB host serial driver library for CDC, FTDI, Arduino and other devices. https://github.com/mik3y/usb-serial-for-android
[40] AGENT.md vs AGENTS.md · Issue #2034 · sst/opencode - GitHub https://github.com/sst/opencode/issues/2034
[41] Workflow runs · mathieudutour/github-tag-action https://github.com/mathieudutour/github-tag-action/actions
[42] How to get real `sys.stdout`? · Issue #8775 · pytest-dev/pytest https://github.com/pytest-dev/pytest/issues/8775
[43] just-tags/ at main · kaphacius/just-tags https://github.com/kaphacius/just-tags
[44] Build software better, together https://github.com/topics/jumia
[45] agentsmd/agents.md https://github.com/agentsmd/agents.md
[46] GitHub - Flet/github-slugger: :octocat: Generate a slug just like GitHub does for markdown headings. https://github.com/Flet/github-slugger
[47] Iptv-org https://github.com/iptv-org
[48] ivawzh/agents-md: Scale your AI agent context ... https://github.com/ivawzh/agents-md
[49] Actions · sbooth/Tag https://github.com/sbooth/Tag/actions
[50] GitHub - ben-sb/obfuscator-io-deobfuscator: A deobfuscator for scripts obfuscated by Obfuscator.io https://github.com/ben-sb/obfuscator-io-deobfuscator
[51] AGENTS.md — a simple, open format for guiding coding agents https://github.com/openai/agents.md
[52] A Computational Analysis of Real-World DJ Mixes using Mix-To-Track Subsequence Alignment https://www.academia.edu/127697159/A_Computational_Analysis_of_Real_World_DJ_Mixes_using_Mix_To_Track_Subsequence_Alignment
[53] What is AGENTS.md and Why Should You Care? - DEV Community https://dev.to/proflead/what-is-agentsmd-and-why-should-you-care-3bg4
[54] Virtual DJ - CDJ Flash Drive Export / Hashtag, Quick & Color Filters - VDJHow2 e24 https://www.youtube.com/watch?v=tbQVIHA_mHk
[55] AUR (en) - tageditor - Arch Linux https://aur.archlinux.org/packages/tageditor
[56] The Dj to Fashion Pipeline | AMARIJASZ https://www.youtube.com/watch?v=-cFkZmzfZcM
[57] WWW.TAGSLUT.COM 网站分析 https://www.openadmintools.com/zh-cn/www.tagslut.com/
[58] Twopercent - Pipeline (Original Mix) [MMXVAC] | Music & Downloads on Beatport https://www.beatport.com/track/pipeline/19654710
[59] Agents.md: A Comprehensive Guide to Agentic AI ... https://differ.blog/p/agents-md-a-comprehensive-guide-to-agentic-ai-collaboration-ff1409
[60] An Essential Guide To Organising Your Music Library - Digital DJ Tips https://www.digitaldjtips.com/music-library-organisation-part-4/

