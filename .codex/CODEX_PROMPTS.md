# Codex Prompts for tagslut DJ Pipeline Verification
## Token-Efficient | Clear | Concise

---

## PROMPT 1: Verify CHANGELOG Claims (Task 0.1)

**Tokens: ~120 | Time: 30 min**

```
@AGENT.md @.codex/CODEX_AGENT.md @CHANGELOG.md

Task: Verify CHANGELOG.md Unreleased section claims about DJ pipeline.

Check:
1. tagslut/exec/mp3_build.py — exists? has build/reconcile functions?
2. tagslut/dj/admission.py — exists? has admit/backfill/validate?
3. tagslut/dj/xml_emit.py — exists? has manifest hash logic?
4. tagslut/storage/migrations/0010_add_dj_pipeline_tables.sql — matches DB_V3_SCHEMA.md?
5. tests/dj/test_dj_pipeline_e2e.py — exists? E2E tests present?
6. tests/exec/test_precheck_dj_contract.py — exists? P0 contract tests present?

Output: Markdown report with:
- File existence ✓/❌
- Function signatures (code snippet)
- Test names + pass/fail status
- Any CHANGELOG claim mismatches

Do NOT modify code.
```

---

## PROMPT 2: Audit CLI Help Text (Task 0.2)

**Tokens: ~110 | Time: 20 min**

```
@AGENT.md @README.md

Task: Audit CLI help text parity with documented 4-stage pipeline.

Run & capture output:
1. tools/get --help — grep "dj" section
2. tagslut mp3 --help — check for "build" and "reconcile"
3. tagslut dj --help — check for "admit", "backfill", "validate", "xml"

Output: Markdown table with:
| Command | Expected (from README.md) | Actual (--help) | Match? |

Note any:
- Legacy language (e.g., "dj" as primary, not deprecated)
- Missing stage descriptions
- Outdated examples

Do NOT modify CLI code.
```

---

## PROMPT 3: Trace DJ Execution Paths (Task 0.3)

**Tokens: ~130 | Time: 45 min**

```
@.codex/CODEX_BOOTSTRAP_REPORT.md#Gap1 @docs/audit/DJ_WORKFLOW_TRACE.md

Task: Execute tools/get --dj under two conditions. Document divergences.

Setup:
- V3_DB="/path/to/music_v3.db" (existing v3 DB)
- NEW_TRACK="<beatport|tidal|spotify URL>" (not in DB)
- EXISTING_TRACK="<URL for track already in DB>" (precheck-hit scenario)

Execute & capture stderr/stdout:
1. tools/get $NEW_TRACK --dj --verbose
   → Document: download phase, promotion phase, MP3 build phase
   
2. tools/get $EXISTING_TRACK --dj --verbose
   → Document: precheck decision, alternate path taken (if any), MP3 outcome

Output: Markdown with:
- Stage execution order (both paths)
- Code path called (e.g., promotion_fed vs precheck_inventory_dj)
- MP3 output difference (if any)
- Match against DJ_WORKFLOW_TRACE.md documented paths

Include command output (captured, not code).
```

---

## PROMPT 4: Write P0 Contract Tests (Task 1.1)

**Tokens: ~140 | Time: 1–2 hours**

```
@AGENT.md @.codex/CODEX_BOOTSTRAP_REPORT.md#Gap1 @MISSING_TESTS.md

Task: Write tests for tools/get --dj contract (P0 priority).

Tests to write in tests/exec/test_precheck_dj_contract.py:

P0-A: Empty PROMOTED_FLACS_FILE
- Fixture: run promotion that yields zero FLACs
- Action: invoke tools/get --dj at DJ stage with empty list
- Assert: exits with error (not silent success) OR logs explicit "zero DJ output"

P0-B: Precheck-Hit Path Exists
- Fixture: seed DB with existing tracks, precheck will match
- Action: run tools/get <url> --dj where precheck returns "already have"
- Assert: DJ path executes (don't fail on precheck-hit)

P0-C: Both Paths Produce Equivalent Admission
- Fixture: same track, run promotion-fed path AND precheck-hit path
- Action: compare resulting dj_admission rows
- Assert: identical dj_admission state OR explicitly document intentional divergence

Constraints:
- Use existing test fixtures in tests/fixtures/
- Mock DB operations if needed (don't modify live DB)
- Keep tests under 50 lines each
- Run: poetry run pytest -q tests/exec/test_precheck_dj_contract.py

Output: Test file with all 3 tests passing or clear failure reasons.
```

---

## PROMPT 5: Write P1 E2E Tests (Task 1.2)

**Tokens: ~150 | Time: 2–3 hours**

```
@AGENT.md @.codex/CODEX_BOOTSTRAP_REPORT.md#Gap4 @MISSING_TESTS.md

Task: Write E2E tests for 4-stage DJ pipeline determinism & safety (P1 priority).

Tests to write in tests/dj/test_dj_pipeline_e2e.py:

P1-A: Retroactive MP3 Admission (New)
- Fixture: 10 MP3 files in temp dir, unregistered
- Action: mp3 reconcile → dj backfill → dj validate
- Assert: all 10 matched to identities, admitted to DJ, validation passes
- Assert: reconcile_log has 20+ rows (2 per file: link + decision)

P1-B: XML Determinism (New)
- Fixture: stable dj_admission + dj_track_id_map state (no changes)
- Action: dj xml emit → [no DB changes] → dj xml emit again
- Assert: both XML files byte-identical (hash match)

P1-C: XML Patch Preserves TrackIDs (New)
- Fixture: prior emit with manifest_hash in dj_export_state
- Action: admit new track to dj_admission → patch (re-emit)
- Assert: existing TrackIDs unchanged, new track gets fresh ID
- Assert: manifest hash updated

P1-D: Patch Fails on Tampered XML (New)
- Fixture: prior emit with stored manifest_hash
- Action: corrupt on-disk XML → run patch
- Assert: patch fails with manifest mismatch error (loud failure)

Constraints:
- Use artifact DB snapshots in artifacts/db/
- Do NOT modify live music_v3.db
- Keep tests under 80 lines each
- Run: poetry run pytest -q tests/dj/test_dj_pipeline_e2e.py -v

Output: Test file with all 4 tests passing or clear failure analysis.
```

---

## PROMPT 6: Update CLI Help Text (Task 1.4)

**Tokens: ~100 | Time: 20 min**

```
@AGENT.md @README.md

Task: Update CLI help text to mark --dj deprecated and reference 4-stage pipeline.

Files to edit:
1. tools/get (or tools/get.py / get.sh) — find help/usage text for --dj
2. tagslut/cli/commands/dj.py (or similar) — help text for dj subcommands

Changes:
1. tools/get --help:
   Mark --dj as DEPRECATED
   Add: "Use 4-stage pipeline instead: see docs/DJ_WORKFLOW.md"
   
2. tagslut dj --help:
   Ensure subcommands listed: admit, backfill, validate, xml emit, xml patch
   Add example: tagslut dj backfill --db <path>

3. tagslut mp3 --help:
   Ensure subcommands listed: build, reconcile
   Add example: tagslut mp3 reconcile --db <path> --mp3-root <path>

Output: Updated CLI help text (screenshot or command output).

Verify:
- tools/get --help | grep -A2 "\-\-dj"
- tagslut dj --help | grep -E "(admit|backfill|validate|xml)"
- tagslut mp3 --help | grep -E "(build|reconcile)"

Do NOT modify functionality, only help text.
```

---

## PROMPT 7: Fix Import Layering (Task 2.2)

**Tokens: ~90 | Time: 30 min**

```
@AGENT.md

Task: Add flake8 import linting rule to enforce tagslutcore → tagslutdj separation.

Check current state:
1. grep -r "from tagslutdj\|import tagslutdj" tagslutcore/ 2>/dev/null | grep -v __pycache__
   → List any violations

2. pip list | grep flake8
   → Check if flake8-allowed-imports installed

Implement rule:
1. Add to setup.cfg or .flake8:
   [flake8]
   allowed-modules = tagslutcore,tagslut.storage,tagslut.db
   
2. Test: poetry run flake8 tagslut/ --select=E999,F999
   → Verify rule loads without error

3. Run on codebase: poetry run flake8 tagslut/ --select=<rule>
   → Verify no violations

Output: Updated config file + test run output.

Constraint: Layering rule must pass current code WITHOUT violations first (may need to fix violations separately).
```

---

## PROMPT 8: Schema Migration Safety (Task 2.4)

**Tokens: ~110 | Time: 20 min**

```
@AGENT.md @docs/DB_V3_SCHEMA.md

Task: Verify migration 0010 checkpoint is mandatory and checkpoints are tracked.

Check:
1. tagslut/storage/migrations/0010_add_dj_pipeline_tables.sql — exists?
2. data/checkpoints/reconcile_schema_0010.json — exists?
3. git log --oneline --all -- "*0010*" — recent migration commits?

Verify checkpoint requirement:
1. Search for "checkpoint" in migration code
2. Confirm pre/post validation runs (PRAGMA foreign_keys, PRAGMA integrity_check)
3. Check backup naming convention (pre_migration_YYYYMMDD_HHMMSS.bak)

Output: Markdown report with:
- Migration 0010 status (applied? when?)
- Checkpoint file location + contents (first 20 lines)
- Pre/post validation rules present? ✓/❌
- Backup naming matches AGENT.md rules? ✓/❌

Do NOT run migration.
```

---

## PROMPT 9: Phase 1 Stack Status (Quick Check)

**Tokens: ~80 | Time: 10 min**

```
@docs/PHASE1_STATUS.md

Task: Quick status of Phase 1 PR stack (no modifications).

Run:
git fetch origin
git log --oneline --graph --max-count=30 origin/dev..HEAD
git log --oneline --graph --max-count=5 HEAD..origin/dev

Check PHASE1_STATUS.md for:
1. PR #193 fix/migration-0006 — status (in progress, merged, waiting)?
2. PR #185 fix/identity-service — status?
3. PR #186 fix/backfill-v3 — status?
4. Dependencies: do PRs have correct depend-on edges?

Output: Markdown with:
- Current gate (which PR is blocking?)
- Estimated time to unblock
- Recommended next action

Do NOT merge or rebase anything.
```

---

## PROMPT 10: Run Baseline Tests (Always First)

**Tokens: ~60 | Time: 15 min**

```
@AGENT.md

Task: Establish baseline test state before any work.

Run:
1. poetry run pytest -q
   → Save output (pass count, fail count, warnings)
   
2. poetry run flake8 tagslut/ tests/ --count
   → Save violation count

3. poetry run mypy tagslut/ --ignore-missing-imports 2>&1 | tail -20
   → Save error count

Output: Baseline report with:
- Test count (passed, failed, warnings) — should match ~579 passed, 2 failed, 1 warning from 2026-03-08
- Flake8 violations
- Mypy errors

This is your reference baseline. All Phase 0 work should not degrade these numbers.
```

---

## Quick Reference: Prompt Selection by Task

| Task | Prompt | Time | Output |
|------|--------|------|--------|
| 0.1 Verify CHANGELOG | Prompt 1 | 30 min | Verification report |
| 0.2 Audit CLI help | Prompt 2 | 20 min | Help text audit table |
| 0.3 Trace DJ paths | Prompt 3 | 45 min | Execution trace with diffs |
| 1.1 Write P0 tests | Prompt 4 | 1–2 hrs | test_precheck_dj_contract.py |
| 1.2 Write P1 tests | Prompt 5 | 2–3 hrs | test_dj_pipeline_e2e.py |
| 1.4 Update CLI help | Prompt 6 | 20 min | Updated --help text |
| 2.2 Fix import layering | Prompt 7 | 30 min | .flake8 config + test output |
| 2.4 Schema checkpoints | Prompt 8 | 20 min | Migration safety report |
| Quick: Phase 1 status | Prompt 9 | 10 min | Stack status |
| Always first: Baseline | Prompt 10 | 15 min | Baseline metrics |

---

## Usage Pattern

### Session Start

```
@AGENT.md @.codex/CODEX_BOOTSTRAP_REPORT.md @.codex/CODEX_AGENT.md

Starting Phase 0 verification. First, run Prompt 10 (baseline).
```

Then paste **Prompt 10** into Codex.

### For Each Task

Paste the corresponding prompt from above. Example:

```
[Paste Prompt 1 here to verify CHANGELOG claims]
```

Codex will:
1. Load referenced files
2. Execute task
3. Produce output
4. Stay within token budget

### Token Budget Per Prompt

- Prompts 1–3: ~110–140 tokens input, expect ~500 tokens output (reports)
- Prompts 4–5: ~140–150 tokens input, expect ~2000 tokens output (code + tests)
- Prompts 6–10: ~60–110 tokens input, expect ~300–800 tokens output (config/status)

**Total for Phase 0 (~5 prompts): ~10k tokens**

---

## Copy-Paste Ready

Save this file in your repo:

```bash
cp codex_prompts.md /Users/georgeskhawam/Projects/tagslut/.codex/CODEX_PROMPTS.md
```

Then in Codex, reference it:

```
@.codex/CODEX_PROMPTS.md

Show me Prompt 1 (Verify CHANGELOG claims).
```

Or just copy a prompt directly into Codex chat.
