You are an expert Python/Bash engineer working in the tagslut repository.

Goal:
Fix `--resume` mode so that re-running a fully-precheck-hit URL produces enrichment,
DJ export, and a clean run summary with no spurious stash/discard entries.

═══════════════════════════════════════════════════════
CONTEXT: Read these first, in order
═══════════════════════════════════════════════════════

Agent instructions:
  AGENT.md
  CLAUDE.md

Primary implementation target:
  tools/get-intake
  tools/get

Supporting scripts (read, likely do not modify):
  tools/review/post_move_enrich_art.py
  tools/review/plan_move_skipped.py
  tools/review/move_from_plan.py

Existing tests for reference:
  tests/exec/
  tests/conftest.py

═══════════════════════════════════════════════════════
OPERATING RULES
═══════════════════════════════════════════════════════

- Follow AGENT.md and CLAUDE.md in all decisions.
- Minimal, reversible patches only. No refactors outside scope.
- Plan before editing: output a verification block in the conversation before touching any file.
- Commit after each step with a conventional message.
- Do not touch database files, migrations, schema, or external volumes.
- Do not modify tagslut.exec.get_intake_console (the Rich wrapper).
- Targeted pytest only: poetry run pytest tests/exec/test_resume_refresh.py -v

═══════════════════════════════════════════════════════
BASELINE
═══════════════════════════════════════════════════════

Run this first and capture the full run summary output before reading any code:

  tools/get --enrich --resume --dj \
    https://www.beatport.com/chart/curation-best-of-2025-nu-disco-disco/873300

Expected broken state:
  Promoted   = 0
  Stash      = 1   (spurious)
  DJ exports = 0
  Discard    = 1   (spurious)
  Enrich/art = skipped

This is your before-state. Keep it for the final diff.

═══════════════════════════════════════════════════════
CONFIRMED ROOT CAUSES
═══════════════════════════════════════════════════════

These have been verified against the source. Read the relevant sections of
tools/get-intake to confirm line numbers before editing anything.

── Root cause 1: PROMOTED_FLACS_FILE is empty in resume runs ──────────────────

PROMOTED_FLACS_FILE is populated exclusively from $PROMOTE_PLAN MOVE-action rows
(inline Python block after "Apply plans"). When PROMOTE_MOVE=0 the file is empty.

Both downstream consumers bail:
  post_move_enrich_art.py: if [[ ! -s "$PROMOTED_FLACS_FILE" ]]; then … skipping
  DJ export block:         DJ_INPUT_COUNT=0 → WARNING: no promoted files

Fix: after the PROMOTED_AUDIO_COUNT / PROMOTED_FLACS_COUNT assignments, add a
resume supplement block gated on RESUME_MODE=1 and PROMOTED_FLACS_COUNT=0:

  if [[ "$RESUME_MODE" -eq 1 && "$PROMOTED_FLACS_COUNT" -eq 0 && -d "$BATCH_ROOT" ]]; then
    echo "Resume mode: supplementing promoted lists from existing batch root files."
    while IFS= read -r resume_path; do
      [[ -n "$resume_path" ]] || continue
      echo "$resume_path" >> "$PROMOTED_AUDIO_FILE"
      echo "$resume_path" >> "$PROMOTED_FLACS_FILE"
    done < <(find "$BATCH_ROOT" -type f -iname '*.flac' | sort)
    PROMOTED_FLACS_COUNT="$(wc -l < "$PROMOTED_FLACS_FILE" | tr -d ' ')"
    PROMOTED_AUDIO_COUNT="$(wc -l < "$PROMOTED_AUDIO_FILE" | tr -d ' ')"
    echo "Resume supplement: $PROMOTED_FLACS_COUNT FLAC(s) from batch root."
  fi

Do NOT change the interface of post_move_enrich_art.py. It expects absolute file
paths, not identity keys. No changes to that script are required.

── Root cause 2: DJ export fallback broken in --dj-only runs ──────────────────

The DJ export step has a fallback to $ROON_M3U_INPUT_FILE when PROMOTED_FLACS_FILE
is empty — but $ROON_M3U_INPUT_FILE only exists when M3U_MODE=1 ran in the same
execution. With --dj and no --m3u the fallback never fires.

Fix: root cause 1 resolves this automatically — after supplementing
PROMOTED_FLACS_FILE, DJ_INPUT_COUNT will be non-zero. Verify this after
implementing root cause 1 before adding any additional code here.

── Root cause 3: Spurious discard plan for dest_exists in resume mode ─────────

plan_move_skipped.py runs unconditionally and builds a discard plan for dest_exists
items. In resume mode a file already at its destination is correct and expected.
The stash=1 / skipped_exists=1 / discard=1 report is misleading noise.

Fix: wrap the --include-buckets "dest_exists" invocation of plan_move_skipped.py
and its corresponding move_from_plan.py execution in:

  if [[ "$RESUME_MODE" -eq 0 ]]; then … fi

The fix-skips plan (missing_tags,path_too_long,conflict_same_dest) is still valid
in resume mode — leave it unchanged.

═══════════════════════════════════════════════════════
PRE-PATCH VERIFICATION (output in conversation before editing any file)
═══════════════════════════════════════════════════════

Read tools/get-intake and output a plan block covering:

1. Exact line range where PROMOTED_FLACS_FILE is written (inline Python block).
2. Exact guard condition on the post_move_enrich_art.py launch.
3. Whether $ROON_M3U_INPUT_FILE is in scope at the DJ export block without M3U_MODE=1.
4. Which plan_move_skipped.py call uses --include-buckets "dest_exists".
5. Confirmation that RESUME_MODE is set before these blocks execute.

Do not edit any file until this output is in the conversation.

═══════════════════════════════════════════════════════
IMPLEMENTATION ORDER
═══════════════════════════════════════════════════════

Step 1 — Root cause 3 (no dependencies, isolated guard):
  Wrap the dest_exists discard plan call and its move execution in RESUME_MODE=0 guard.
  Commit: fix(intake): suppress dest_exists discard plan in resume mode

Step 2 — Root cause 1 (core fix):
  Add the resume supplement block as specified above immediately after the
  PROMOTED_AUDIO_COUNT / PROMOTED_FLACS_COUNT assignments.
  Commit: fix(intake): supplement promoted file lists from batch root in resume mode

Step 3 — Root cause 2 (verify only, patch if needed):
  Re-run the baseline command. Confirm DJ_IDENTITY_COUNT > 0.
  If still 0, wire the precheck decisions CSV inventory fallback into the DJ
  paths file construction gated on RESUME_MODE=1, using the same skip-row
  path logic already present in the Roon M3U step.
  Commit if needed: fix(intake): wire DJ export fallback to inventory in resume mode

═══════════════════════════════════════════════════════
TESTS
═══════════════════════════════════════════════════════

Add tests/exec/test_resume_refresh.py with three unit tests.
No real DB writes. No external volume access. Follow fixture patterns in tests/.

Test 1 — Resume skips redownload of already-staged files
  Fixture: precheck artifact 35 tracks all decision=skip, BATCH_ROOT has 35 FLACs,
           PROMOTE_MOVE=0.
  Assert:  download step not invoked (mock bpdl/tiddl);
           PROMOTED_FLACS_FILE contains 35 paths after supplement block.

Test 2 — Resume runs enrichment over existing batch files
  Same fixture. RESUME_MODE=1, TAGGING_MODE=1, EXECUTE=1.
  Assert:  post_move_enrich_art.py invoked with non-empty --paths-file
           containing the 35 batch-root FLAC paths.

Test 3 — dest_exists does not generate discard plan in resume mode
  Fixture: PROMOTE_PLAN with one MOVE row where dest already exists. RESUME_MODE=1.
  Assert:  plan_move_skipped.py not called with --include-buckets "dest_exists";
           fix-skips variant (missing_tags,path_too_long,conflict_same_dest) still called.

Run new tests:
  poetry run pytest tests/exec/test_resume_refresh.py -v

Confirm existing suite:
  poetry run pytest tests/ -x -q

═══════════════════════════════════════════════════════
EXIT CRITERIA
═══════════════════════════════════════════════════════

Re-run the baseline command. The run summary must show:

  PROMOTED_FLACS_COUNT > 0   (batch files supplemented)
  Discard = 0                (no spurious dest_exists plan)
  DJ_IDENTITY_COUNT > 0      (export fired)
  Enrich/art pid = ...       (background process launched)

Default (no --resume) run on the same URL must produce output identical
to the original baseline captured at the start.

All three new tests pass.
Full existing test suite passes.

═══════════════════════════════════════════════════════
COMMIT AND SYNC
═══════════════════════════════════════════════════════

After all steps:

  git status
  git diff
  git add tools/get-intake tools/review/post_move_enrich_art.py \
          tests/exec/test_resume_refresh.py
  git commit -m "fix(intake): resume mode enrichment, DJ export, and discard plan suppression"

If any file under docs/ was updated, apply the identical patch to both
CLAUDE.md (repo root) and .claude/CLAUDE.md and include them in the commit.
