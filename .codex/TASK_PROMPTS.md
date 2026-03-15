# TASK_PROMPTS.md — Master Task Index

**Last Updated:** 2026-03-15 14:55 UTC
**Phase:** Phase 1 (Closure)  
**Usage:** Copy prompt for current task, paste into Codex, execute, commit, update status below, repeat.

---

## Status Overview

| Task | Title | Status | Est. Time | Completed |
|------|-------|--------|-----------|-----------|
| 1.1 | Write P0 Contract Tests | ✅ COMPLETE | 1–2 hrs | 2026-03-15 |
| 1.2 | Write P1 E2E Tests | ✅ COMPLETE | 2–3 hrs | 2026-03-15 |
| **1.3** | **Normalize Docs (4-Stage Contract)** | **⏳ READY** | **1–2 hrs** | — |
| 1.4 | Update CLI Help Text | ⏳ READY (on 1.3) | 20 min | — |
| 2.1 | Deprecate tools/get --dj | ⏸️ BLOCKED (on 1.4) | 30 min | — |
| 2.2 | Enforce Import Layering | ⏸️ BLOCKED (on 2.1) | 30 min | — |

---

# Task 1.3: Normalize Docs Around Single 4-Stage Contract

**Status:** ⏳ READY  
**Estimated Time:** 1–2 hours  
**Blocker:** None (can start now)  
**Unblocks:** Task 1.4 (CLI help updates)  

**Goal:** Ensure all documentation consistently presents the 4-stage DJ pipeline as canonical and `tools/get --dj` as deprecated legacy. Operators should never encounter conflicting guidance.

---

## Prompt for Task 1.3

```
@AGENT.md @README.md @.codex/CODEX_BOOTSTRAP_REPORT.md

Task: Normalize all documentation to consistently present the 4-stage DJ pipeline as canonical and tools/get --dj as deprecated legacy.

Current State:
- CHANGELOG.md claims 4-stage pipeline (mp3 build/reconcile, dj admit/backfill/validate, dj xml emit/patch)
- DJ_WORKFLOW_AUDIT.md documents why tools/get --dj is broken (two hidden paths, no durable MP3 abstraction)
- But: some docs still reference --dj as primary, or don't mention the 4-stage alternative

Execution:

1. IDENTIFY CONFLICTING DOCS
   - Search for any reference to "tools/get --dj" that doesn't mark it as deprecated
   - Search for any DJ workflow documentation that doesn't mention the 4-stage pipeline
   - Files to check: README.md, docs/DJ_WORKFLOW.md, .codex/*.md, docstrings in dj.py, mp3.py, tools/get

2. CREATE DEPRECATION NOTICE
   - Write canonical deprecation block (1–2 paragraphs):
     * "tools/get --dj is deprecated. Use the 4-stage DJ pipeline instead."
     * Link to DJ_WORKFLOW.md
     * Example: "tagslut mp3 reconcile → tagslut dj backfill → tagslut dj validate → tagslut dj xml emit"

3. UPDATE OR ARCHIVE CONFLICTING DOCS
   - README.md DJ section:
     * Replace any "--dj" section with "4-Stage DJ Pipeline" section
     * Include deprecation notice
     * Show all four stages with example commands
     * Link to DJ_WORKFLOW.md for details
   
   - Any docs/DJ*.md that reference --dj:
     * Add deprecation notice at top
     * Add "See DJ_WORKFLOW.md for canonical pipeline" link

4. CREATE OR REFRESH DJ_WORKFLOW.md (Canonical Reference)
   - Sections:
     * Overview: "The 4-stage DJ pipeline is the only supported workflow"
     * Stage 1: MP3 Registration (mp3 build vs mp3 reconcile)
     * Stage 2: DJ Admission (admit vs backfill)
     * Stage 3: DJ Validation (dj validate)
     * Stage 4: Rekordbox Export (dj xml emit, dj xml patch)
     * Why the 4-stage model (reference DJ_WORKFLOW_AUDIT.md for diagnosis)
     * Deprecation: "tools/get --dj is deprecated (see CHANGELOG.md)"
   - Should be readable without reading other docs

5. VERIFY CONSISTENCY
   - Run: grep -r "tools/get --dj\|--dj" docs/ README.md .codex/ —include="*.md"
   - Every mention should either:
     * Be in a "DEPRECATED" section, OR
     * Include "See DJ_WORKFLOW.md for the canonical 4-stage pipeline"
   - No .md file should present --dj as the primary DJ workflow

Output:
- Updated README.md (with 4-stage DJ section)
- Updated or archived DJ docs
- Created or refreshed DJ_WORKFLOW.md (canonical reference)
- Grep report showing all remaining --dj references (all should be marked deprecated)

Do NOT modify code, only docs.
```

---

# Task 1.4: Update CLI Help Text

**Status:** ⏸️ BLOCKED (on 1.3)  
**Estimated Time:** 20 minutes  
**Blocker:** Task 1.3 must complete first  
**Unblocks:** Task 2.1  

## Prompt for Task 1.4

```
@AGENT.md @README.md @docs/DJ_WORKFLOW.md

Task: Update CLI help text to mark --dj deprecated and reference 4-stage pipeline.

Files to edit:
1. tools/get (or tools/get.py / get.sh) — find help/usage text for --dj
2. tagslut/cli/commands/dj.py (or similar) — help text for dj subcommands
3. tagslut/cli/commands/mp3.py (or similar) — help text for mp3 subcommands

Changes:

1. tools/get --help:
   - Mark --dj as DEPRECATED (red or warning style if supported)
   - Add: "Use 4-stage pipeline instead: see docs/DJ_WORKFLOW.md"
   
2. tagslut dj --help:
   - Ensure subcommands listed: admit, backfill, validate, xml emit, xml patch
   - Add example: tagslut dj backfill --db <path>

3. tagslut mp3 --help:
   - Ensure subcommands listed: build, reconcile
   - Add example: tagslut mp3 reconcile --db <path> --mp3-root <path>

Verify after changes:
- tools/get --help | grep -A2 "\-\-dj" (should show DEPRECATED)
- tagslut dj --help | grep -E "(admit|backfill|validate|xml)"
- tagslut mp3 --help | grep -E "(build|reconcile)"

Output: Updated CLI help text (captured command output).

Do NOT modify functionality, only help text.
```

---

# Task 2.1: Deprecate or Rewire tools/get --dj

**Status:** ⏸️ BLOCKED (on 1.4)  
**Estimated Time:** 30 minutes  
**Blocker:** Task 1.4 must complete first  
**Unblocks:** Task 2.2  

## Prompt for Task 2.1

```
@AGENT.md @CHANGELOG.md

Task: Enforce tools/get --dj deprecation (hard error or thin wrapper).

Current State:
- tools/get --dj has two hidden code paths (promotion-fed vs precheck-hit)
- DJ_WORKFLOW_AUDIT.md documents why this is broken
- CLI help now marks it as deprecated (Task 1.4)

Choose one option and implement:

OPTION A (Recommended First): Hard Deprecation
- At startup of tools/get --dj, print error to stderr:
  "ERROR: tools/get --dj is deprecated and will be removed in v3.1.
   Use the 4-stage DJ pipeline instead:
   1. tagslut mp3 reconcile --db <DB> --mp3-root <DJ_ROOT>
   2. tagslut dj backfill --db <DB>
   3. tagslut dj validate --db <DB>
   4. tagslut dj xml emit --db <DB> --output rekordbox.xml
   
   See docs/DJ_WORKFLOW.md for details."
- Exit with code 1 (fail immediately)
- Document in CHANGELOG.md: "Removed: tools/get --dj (use 4-stage pipeline)"

OPTION B (Long-term): Thin Wrapper
- Rewire tools/get --dj to invoke:
  - mp3 reconcile (or mp3 build if no existing MP3s)
  - dj backfill
  - dj validate
  - dj xml emit
- Document as "tools/get --dj is a convenience alias for the 4-stage pipeline"
- Test both old path (--dj) and new stages produce identical results

Output: Chosen option implemented, tested, and committed.

Do NOT leave two paths in place.
```

---

# Task 2.2: Enforce Import Layering

**Status:** ⏸️ BLOCKED (on 2.1)  
**Estimated Time:** 30 minutes  
**Blocker:** Task 2.1 must complete first  
**Unblocks:** Nothing (end of Phase 1)  

## Prompt for Task 2.2

```
@AGENT.md

Task: Add flake8 import linting rule to enforce tagslutcore → tagslutdj separation.

Current State:
- AGENT.md documents import layering rules
- No linting rule enforces them yet

Check current state:
1. grep -r "from tagslutdj\|import tagslutdj" tagslutcore/ 2>/dev/null | grep -v __pycache__
   → List any violations (should be empty)

2. grep -r "from tagslutcore\|import tagslutcore" tagslutdj/ 2>/dev/null | grep -v __pycache__
   → List any violations (should be empty)

3. pip list | grep flake8
   → Check if flake8-allowed-imports installed

Implement linting rule:
1. Check if setup.cfg or .flake8 exists in repo root
   
2. Add (or update) configuration:
   [flake8]
   extend-allowed-imports = tagslutcore,tagslut.storage,tagslut.db
   
   OR use flake8-allowed-imports plugin:
   pip install flake8-allowed-imports
   
   Then add to setup.cfg:
   [flake8]
   allowed-imports = tagslutcore.*,tagslut.storage,tagslut.db

3. Test configuration:
   - poetry run flake8 tagslut/ --count
   - Verify no violations are reported
   - If violations exist, report them (don't fix in this task)

4. Document in AGENT.md (add section):
   "Import Layering (Enforced by Flake8)
    - tagslutcore* can only import from: tagslutcore, tagslut.storage, tagslut.db
    - tagslutdj* can import from: tagslut.*, except not upward to tagslutcore
    - Violations cause CI failure"

Output: Updated .flake8 or setup.cfg, flake8 run output showing clean state.

Do NOT modify code to fix violations (that's a separate task).
```

---

# Old Phase 0 Tasks (Reference)

## Task 0.1: Verify CHANGELOG Claims — ✅ COMPLETE

## Task 0.2: Audit CLI Help Text — ✅ COMPLETE

## Task 0.3: Trace DJ Execution Paths — ✅ COMPLETE

---

# Usage

## Get Next Task Prompt

```bash
# Show current status
grep "^| Task\|^|---" .codex/TASK_PROMPTS.md | head -20

# Get Task 1.3 prompt
sed -n '/^# Task 1.3:/,/^# Task 1.4:/p' .codex/TASK_PROMPTS.md | head -60
```

## After Completing a Task

1. **Run the prompt** in Codex
2. **Commit the output:**
   ```bash
   git add <output_file>
   git commit -m "feat: Task X.Y — <description>"
   ```

3. **Update status in this file:**
   ```bash
   # Edit .codex/TASK_PROMPTS.md
   # Change Task X.Y status from "⏳ READY" to "✅ COMPLETE"
   # Change next Task status from "⏸️ BLOCKED" to "⏳ READY"
   # Update "Last Updated" date at top
   ```

4. **Commit the update:**
   ```bash
   git add .codex/TASK_PROMPTS.md
   git commit -m "docs: Task X.Y complete, Task X+1 ready"
   ```

5. **Copy next task prompt** and repeat

## Quick CLI Reference

```bash
# List all tasks with status
grep "^| [0-9]\." .codex/TASK_PROMPTS.md

# Get a specific task's prompt
grep -A 50 "^# Task 1.3:" .codex/TASK_PROMPTS.md | head -80

# Show which task is ready
grep "⏳ READY" .codex/TASK_PROMPTS.md
```
