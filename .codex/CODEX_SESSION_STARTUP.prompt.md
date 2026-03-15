# Codex Session Startup — tagslut Project

You are working in the tagslut repository at `/Users/georgeskhawam/Projects/tagslut`.

## Mandatory Context Files (Read in This Order)

1. AGENT.md — Vendor-neutral canonical instruction file
2. .codex/CODEX_BOOTSTRAP_REPORT.md — This session's full operating manual
3. .codex/CODEX_AGENT.md — Codex-specific procedural rules (if different from AGENT.md)

## Operating Mode: Verification-First

Your mission is NOT to redesign the project. Your mission is to **verify the documented 4-stage DJ pipeline is true everywhere and complete the missing pieces.**

Before any code work:
- [ ] Read AGENT.md (sections 1–3)
- [ ] Skim CODEX_BOOTSTRAP_REPORT.md Part 1 (Strategic Overview)
- [ ] Read the specific task assignment below

## Current Phase: Verification (Phase 0)

You are in Phase 0: Verification. Your tasks are from the CODEX_BOOTSTRAP_REPORT.md Task List.

### Your Task Assignment (Choose One)

**If verifying CHANGELOG claims:**
```
See: CODEX_BOOTSTRAP_REPORT.md → Part 2 → Section 10.0 → Task 0.1
Files to verify:
  - tagslut/exec/mp3_build.py
  - tagslut/dj/admission.py
  - tagslut/dj/xml_emit.py
  - tagslut/storage/migrations/0010_add_dj_pipeline_tables.sql
  - tests/ (look for test_dj_pipeline_e2e.py, test_precheck_dj_contract.py)
Produce: Verification report with code snippets
```

**If auditing CLI help text:**
```
See: CODEX_BOOTSTRAP_REPORT.md → Part 2 → Section 10.0 → Task 0.2
Commands to check:
  - tools/get --help (is --dj marked deprecated?)
  - tagslut mp3 --help (does it describe build/reconcile?)
  - tagslut dj --help (does it list all 4 stages?)
Produce: CLI help audit report with diffs
```

**If tracing actual DJ execution:**
```
See: CODEX_BOOTSTRAP_REPORT.md → Part 2 → Section 10.0 → Task 0.3
Commands to run:
  - tools/get <url> (non-DJ path)
  - tools/get <url> --dj (promotion-fed path)
  - [trigger precheck-hit condition]
  - tools/get <url> --dj (precheck-hit path)
Document divergences.
Produce: Execution trace report
```

## Constraint Rules (Non-Negotiable)

### Primary Rules (From CODEX_BOOTSTRAP_REPORT.md Part 3)

- ✅ Trust AGENT.md as primary source; defer to it when uncertain
- ✅ Write DJ changes to dj_* tables, not files.dj_* columns
- ✅ Link DJ state to track_identity via identity_id
- ✅ Use explicit commands (tagslut mp3, tagslut dj) instead of hidden paths
- ✅ Enforce dry-run by default; require explicit --execute
- ✅ Run migration verification checklist before/after schema changes

### Safety Rails (Anti-Patterns)

- ❌ Don't assume tools/get --dj reliability (two paths exist)
- ❌ Don't assume enrichment timing (--dj suppresses background enrich)
- ❌ Don't mutate files.dj_* columns (legacy; use dj_* tables)
- ❌ Don't assume XML reconstruction is cheap (test patch determinism)
- ❌ Don't skip validation before export
- ❌ Don't use paths as identity anchors (use track_identity.id)

## Pre-Work Checklist

Before touching any code:

- [ ] Verify current branch: `git fetch origin && git log --oneline origin/dev..HEAD`
- [ ] Run baseline tests: `poetry run pytest -q`
- [ ] Run schema check: `make doctor-v3 V3=$TAGSLUT_DB` (if schema-related work)
- [ ] Confirm AGENT.md is dated 2026-03-14 (current)
- [ ] Confirm CHANGELOG.md Unreleased section is synced

## If You Hit a Question

**Ambiguity on what to do?** Check CODEX_BOOTSTRAP_REPORT.md in this order:
1. Part 3: "Constraints for Claude Code"
2. Part 2: Relevant section (10.0, 8.0, 9.0)
3. Part 1: Strategic context

**Ambiguity on what the code should do?** Check in this order:
1. AGENT.md (doctrine)
2. CHANGELOG.md (claimed recent changes)
3. docs/audit/DJ_WORKFLOW_AUDIT.md (gap diagnosis)
4. The code itself (verify against docs)

**Need to verify a claim?** Always prefer:
- Direct code inspection
- Test execution
- DB schema verification
- Over documentation alone

## End Checklist (Before Committing)

After your work:
- [ ] `poetry run pytest -q` (test baseline)
- [ ] `poetry run flake8 tagslut/ tests/` (lint)
- [ ] `poetry run mypy tagslut/ --ignore-missing-imports` (types)
- [ ] `make doctor-v3 V3=$TAGSLUT_DB` (schema check, if applicable)
- [ ] `git diff --cached --name-only` (verify staged files match intent)

---

**Session prepared:** [timestamp]
**Report version:** tagslut_supermassive_report_20260315.md
**Baseline test count:** 579 passed, 2 failed, 1 warning (as of 2026-03-08)
```

---

## Exact Prompt to Paste into Codex at Session Start

### Copy-Paste This Into Codex (VS Code Extension)

When you open Codex in VS Code, paste this into the Codex chat:
```
@AGENT.md @.codex/CODEX_BOOTSTRAP_REPORT.md @.codex/CODEX_AGENT.md

I'm starting a verification session on the tagslut DJ pipeline.

My task: [INSERT YOUR TASK NUMBER FROM ABOVE — e.g., "Task 0.1: Verify CHANGELOG claims"]

I've read AGENT.md, CODEX_BOOTSTRAP_REPORT.md (Part 1 Strategic Overview), and this startup prompt.

My immediate next actions:
1. [Action 1]
2. [Action 2]
3. [Action 3]

Before I proceed, confirm:
- Are there any blocking constraints I'm missing?
- Should I start with [specific file]?
- Are there environment variables I need to check?

Then I'll execute the task and produce [DELIVERABLE TYPE — e.g., "verification report with code snippets"].
```

---

## Exact File Locations Reference
```
# Codex will reference these files by relative path from repo root:

AGENT.md                                  ← Primary config (read first)
CLAUDE.md                                 ← Codex-specific rules
README.md                                 ← Operator overview
CHANGELOG.md                              ← Recent changes (verify claims)

# Under docs/:
docs/DB_V3_SCHEMA.md                      ← Schema ownership
docs/DJ_WORKFLOW.md                       ← Current pipeline
docs/PROGRESS_REPORT.md                   ← Current state (2026-03-14)
docs/PHASE1_STATUS.md                     ← Phase 1 PR chain status

# Under docs/audit/:
docs/audit/DJ_WORKFLOW_AUDIT.md           ← Gap diagnosis (if touching DJ)
docs/audit/DJ_WORKFLOW_TRACE.md           ← Path trace
docs/audit/DJ_WORKFLOW_GAP_TABLE.md       ← Gaps at glance
docs/audit/MISSING_TESTS.md               ← Test priorities
docs/audit/REKORDBOX_XML_INTEGRATION.md   ← XML contract

# Under .codex/ (your new bootstrap files):
.codex/CODEX_BOOTSTRAP_REPORT.md          ← This session's manual
.codex/CODEX_SESSION_STARTUP.prompt.md    ← Session startup (paste into Codex)

# Code to verify (Task 0.1):
tagslut/exec/mp3_build.py                 ← Stage 1 implementation
tagslut/dj/admission.py                   ← Stage 2 implementation
tagslut/dj/xml_emit.py                    ← Stage 4 implementation
tagslut/storage/migrations/0010_*         ← DJ schema

# Tests to check:
tests/dj/test_dj_pipeline_e2e.py          ← E2E tests (claimed in CHANGELOG)
tests/exec/test_precheck_dj_contract.py   ← P0 contract tests
tests/dj/test_admission.py                ← Unit tests
tests/storage/test_mp3_dj_migration.py    ← Migration tests

# Tools to verify (Task 0.2):
tools/get                                 ← Primary downloader
tools/get-intake                          ← Intake backend
tools/review/*                            ← Review utilities
