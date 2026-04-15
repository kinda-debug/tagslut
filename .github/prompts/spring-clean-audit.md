# Codex Prompt: Spring Clean — Repo Audit & Tightening

**Repo**: `kinda-debug/tagslut` | **Branch**: `dev`
**Save this file to**: `.github/prompts/spring-clean-audit.md`

---

## Objective

Audit the entire repo surface — source, tests, tools, scripts, docs, and
prompts — and produce a structured tightening plan. This is a read-and-report
pass first. No code changes until the report is approved by the operator.

The goal: make the repo read like a map, not a maze. Every file should have a
clear owner, a clear purpose, and a clear relationship to the system. Dead
weight gets flagged. Duplication gets flagged. Drift between docs and code gets
flagged. The CLI surface must be internally consistent and self-describing.

---

## Scope

### 1. CLI surface audit (`tagslut/cli/commands/`)

For each command module (`get.py`, `tag.py`, `fix.py`, `auth.py`, `admin.py`,
`index.py`, `dj.py`, `gig.py`, `report.py`, `scan.py`, `ops.py`, `execute.py`,
`export.py`, `verify.py`, `intake.py`, `mp3.py`, `master.py`, `lexicon.py`,
`library.py`, `misc.py`, `provider.py`, `postman.py`, `decide.py`, `v3.py`,
`track_hub_cli.py`):

- List every `@click.command` and `@click.group` it registers.
- Check that the command name, help text, and argument/option names are
  consistent with what `docs/SCRIPT_SURFACE.md` documents.
- Flag any command that:
  - Has no help text or a single-word help text (not self-describing).
  - Is duplicated by another command in a different module.
  - Is referenced in `docs/` or `tools/` but not actually importable via the
    main CLI entry point in `tagslut/cli/main.py`.
  - Calls into `tagslut/exec/` functions that no longer exist or have been
    renamed.

Also audit the helper files: `_auth_helpers.py`, `_enrich_helpers.py`,
`_index_helpers.py`, `_cohort_state.py`. Flag any helper that is defined but
never imported by any command module.

### 2. Tools layer audit (`tools/`)

For every executable in `tools/` (files without `.py` extension treated as
shell wrappers, `.py` files as standalone scripts):

- Classify as: **active** (called by operator or tests), **orphan** (not
  referenced anywhere), or **superseded** (replaced by a CLI command or newer
  tool).
- For `tools/get`, `tools/get-intake`, `tools/tag`, `tools/enrich`,
  `tools/auth`, `tools/tag-run`, `tools/tag-metadata`, `tools/tag-build`,
  `tools/tag-audiofeatures`, `tools/metadata`, `tools/metadata-audit`,
  `tools/get-report`, `tools/get-help`, `tools/beatport`, `tools/tidal`,
  `tools/tiddl`, `tools/deemix`, `tools/mp3_reconcile_scan`,
  `tools/playlist-sync`, `tools/build_dj_seed_from_tree_rbx`,
  `tools/centralize_lossy_pool`: verify the shebang line, check what
  Python/shell entry point they invoke, and verify it still resolves.
- Identify tools in `tools/archive/` that have NOT been superseded and may
  still be needed.
- Identify tools in `tools/review/` that are active vs. dead.

### 3. Scripts layer audit (`scripts/`)

Same classification pass as tools: **active**, **orphan**, **superseded**.

Flag scripts that:
- Live at repo root (not in `scripts/`) as `__pycache__/*.pyc` suggests
  (e.g., `build_rekordbox_xml_from_pool.py`, `filter_spotify_against_db.py`,
  `rebuild_pool_library.py`, `rewrite_rekordbox_db_paths.py`,
  `rewrite_rekordbox_xml_paths.py`) — these are loose root-level scripts that
  should either be in `scripts/rekordbox/` or `tools/`.
- Are duplicated between `scripts/` and `scripts/archive/` or `tools/review/`.
- Reference paths or modules that no longer exist.

### 4. Codex prompt audit (`.github/prompts/`)

For each prompt file:
- Identify its target deliverable (what files/modules it creates or modifies).
- Check whether that deliverable exists and is in the expected state.
- Classify as: **done** (deliverable shipped), **active** (in-flight or
  future), **stale** (target no longer relevant), **orphan** (no clear
  deliverable).
- Flag prompts that lack the "do not recreate existing deliverables" guard.
- Flag prompts that specify an agent identity (violates prompt authoring policy).
- Flag prompts in the archive directory that are not clearly marked as such.

Cross-check against `STAGING_OPS.md` and memory context for which prompts
are known to be ready but not yet executed.

### 5. Docs audit (`docs/`)

For every file in `docs/` (not `docs/archive/`):
- Check whether it describes the current system state or an aspirational/past
  state.
- Flag any doc that contradicts `PROJECT_DIRECTIVES.md` or current schema.
- Flag any doc that has a near-duplicate in `docs/archive/` (indicating the
  live version may itself be stale).
- Specifically verify `docs/SCRIPT_SURFACE.md` against the actual CLI surface
  from step 1.
- Check `docs/STAGING_OPS.md` — does it accurately describe the current staging
  directory structure (`/Volumes/MUSIC/staging/` not `mdl/`)?

### 6. Source module audit (`tagslut/`)

For each subpackage, identify modules that:
- Are imported by nothing (dead modules). Check `__init__.py` exports and
  cross-module imports.
- Have a parallel/duplicate in another subpackage (e.g., `tagslut/exec/` vs
  `tagslut/dj/` overlap in DJ logic).
- Are named inconsistently with the package pattern (e.g. `_web/review_app.py`
  vs `dj/` pattern).
- Contain `TODO`, `FIXME`, or `raise NotImplementedError` stubs that block
  actual functionality.

Pay particular attention to:
- `tagslut/exec/` — this is the largest subpackage; identify which modules are
  actively called by CLI commands vs. dead weight.
- `tagslut/metadata/` — complex with `providers/`, `pipeline/`, `models/`,
  `store/`, `canon/`. Identify whether all sub-dirs have `__init__.py` and
  are importable.
- `tagslut/storage/v3/` — identify whether all migration files in
  `tagslut/storage/migrations/` are reflected in the Alembic chain and
  consistent with `supabase/migrations/`.

### 7. Test layout audit (`tests/`)

Flag:
- Tests that live at `tests/` root but have a logical home in a subdirectory
  (e.g., `tests/test_backfill_identity_v3.py` vs `tests/storage/v3/`).
- Duplicate test coverage: tests in root `tests/` AND `tests/exec/` that cover
  the same module.
- Test files with no assertions (empty or only `pass`).
- Tests that import from `scripts/` or `tools/` directly (brittle coupling).

---

## Grounding pass (MANDATORY — stop and report if any fail)

Before producing the audit report, verify these facts by reading the actual
files. Do not infer from filenames alone.

1. Read `tagslut/cli/main.py` — extract the complete registered command tree.
2. Read `docs/SCRIPT_SURFACE.md` — extract the documented command surface.
3. Read `docs/STAGING_OPS.md` — extract the current staging directory names.
4. Read `.git/logs/HEAD` (last 40 lines) — confirm current branch is `dev`
   and get the most recent commit SHA.
5. Count files in `.github/prompts/` — report the total and list any that are
   in subdirectories.

If any of these reads fail (file missing, unreadable), stop and report the
failure before proceeding.

---

## Deliverable

Produce a single report file at: `docs/SPRING_CLEAN_REPORT_2026.md`

Structure:

```
# Spring Clean Report — 2026-04-15

## Summary
<3-5 sentences on what was found. Total files audited. Major findings.>

## CLI Surface
### Registered commands vs. documented commands
<table: command | module | help present? | in SCRIPT_SURFACE.md? | issues>

### Dead helpers
<list with reason>

### Command consistency issues
<list>

## Tools Layer
### Active tools
<list>
### Orphaned tools
<list — candidate for tools/archive/ or deletion>
### Superseded tools
<list with what supersedes them>

## Scripts Layer
### Active scripts
<list>
### Root-level loose scripts (should be relocated)
<list with proposed destination>
### Orphaned/superseded scripts
<list>

## Codex Prompts
### Done (deliverable shipped)
<list>
### Active (in-flight or scheduled)
<list>
### Stale/orphan
<list with reason>
### Policy violations (missing guard / agent identity)
<list>

## Docs
### Accurate and current
<list>
### Stale or aspirational
<list with specific drift noted>
### Contradictions with PROJECT_DIRECTIVES.md
<list>

## Source Modules
### Dead modules (not imported by anything)
<list>
### Duplicated logic
<list with proposed resolution>
### Stubs blocking functionality
<list>

## Tests
### Misplaced tests (proposed relocation)
<list>
### Duplicate coverage
<list>
### Brittle imports
<list>

## Prioritized action list
<numbered, ordered by impact, scoped to surgical changes>
```

---

## Constraints

- Do not modify any source file, test, doc, or prompt during this pass.
- Do not recreate any file that already exists.
- The report is the only output.
- If a grounding step fails, append a `## Blocked` section to the report
  with the specific failure and stop.
- Targeted pytest only — do not run the full suite.
- Commit the report file when done:
  `docs(audit): spring clean report 2026-04-15`
