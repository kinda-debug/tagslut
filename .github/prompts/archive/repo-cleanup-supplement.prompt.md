This prompt is a SUPPLEMENT to `.github/prompts/repo-cleanup.prompt.md`.
Do not re-run the original prompt. Execute only the tasks defined here.
Read AGENT.md and CLAUDE.md before proceeding.

Last audit: 2026-03-29

═══════════════════════════════════════════════════════
OPERATING RULES (same as base cleanup prompt)
═══════════════════════════════════════════════════════

- Never delete a file without first verifying it is not referenced in:
    .github/workflows/*.yml
    Makefile
    pyproject.toml
    tagslut/ (package)
    tests/
    any active prompt under .github/prompts/
- Prefer archiving over deletion when uncertain.
- Do NOT touch: tagslut/ (package), tests/, tools/get*, supabase/, config/,
  .github/workflows/, pyproject.toml, poetry.lock, rkrdxk3.xml (active Rekordbox XML).
- Commit after each phase. One logical change per commit.
- Produce entries in docs/CLEANUP_MANIFEST.md (append — do not overwrite).

═══════════════════════════════════════════════════════
PHASE A — ROOT JUNK: outright deletion
═══════════════════════════════════════════════════════

These files are confirmed scratch or superseded. Verify each exists, check
it is not referenced anywhere, then delete:

  qqqq.txt
  sdf.dc
  claudebs.md
  tagslut_DIRECTIVES_REVISED_2026-03-26.md   ← superseded by PROJECT_DIRECTIVES.md
  DJ_PIPELINE_FULL_REPAIR_CODEX.md           ← one-off prompt, not in .github/prompts/
  POSTMAN_AI_PROMPT.md                       ← one-off, not in .github/prompts/
  postman-fix-prompt.md                      ← one-off, not in .github/prompts/
  20260317_rekordbox.xml                     ← stale XML export (NOT rkrdxk3.xml — leave that)

For each: run `grep -r "<filename>" . --include="*.py" --include="*.md" \
  --include="*.sh" --include="*.yml" -l` before deleting.
If any reference is found, do not delete — note in manifest as "left in place".

Commit: `chore(cleanup): delete root-level junk from 2026-03-29 audit`

═══════════════════════════════════════════════════════
PHASE B — DUPLICATE PYTHON FILES AT REPO ROOT
═══════════════════════════════════════════════════════

Two copies of process_dedupe.py exist:
  ./process_dedupe.py         ← root-level copy
  ./scripts/process_dedupe.py ← canonical location

1. Diff them: `diff process_dedupe.py scripts/process_dedupe.py`
2. If identical or root copy is older: delete `./process_dedupe.py`.
3. If root copy has unique content not in scripts/: merge into
   `scripts/process_dedupe.py`, then delete root copy.
4. Check that nothing imports or calls `./process_dedupe.py` by path.

Commit: `chore(cleanup): remove duplicate process_dedupe.py from root`

═══════════════════════════════════════════════════════
PHASE C — files/ DIRECTORY
═══════════════════════════════════════════════════════

The `files/` directory has no defined role. Evaluate each entry:

  files/BACKFILL_GUIDE.md
    → Read it. If content is already in docs/ or superseded, delete.
      Otherwise move to docs/.

  files/PROVENANCE_INTEGRATION.md
    → Read it. If content is already in docs/INGESTION_PROVENANCE.md
      or docs/MULTI_PROVIDER_ID_POLICY.md, delete.
      Otherwise move to docs/.

  files/REFACTOR_PLAN.md
    → Read it. If it describes a completed refactor, move to docs/archive/.
      If still relevant, move to docs/.

  files/get-intake-refactored.py
    → Check if any of its logic was promoted into
      tagslut/exec/intake_orchestrator.py or tagslut/cli/commands/intake.py.
      Run: `diff files/get-intake-refactored.py tagslut/exec/intake_orchestrator.py`
      If fully absorbed: delete.
      If partially absorbed or unclear: move to scripts/archive/ with note.

  files/provenance_tracker.py
    → Check if this is imported or referenced anywhere.
      Run: `grep -r "provenance_tracker" . --include="*.py" -l`
      If not referenced: move to scripts/archive/.
      If referenced: move to tagslut/utils/ and update imports.

After processing all entries, delete the `files/` directory if empty.

Commit: `chore(cleanup): process files/ scratch directory`

═══════════════════════════════════════════════════════
PHASE D — SECURITY: tidal_tokens.json
═══════════════════════════════════════════════════════

1. Check .gitignore: `grep tidal_tokens .gitignore`
   If NOT present, add it: `echo "tidal_tokens.json" >> .gitignore`

2. Check if it was ever committed to git history:
   `git log --all --full-history -- tidal_tokens.json`
   If it appears in history: do NOT attempt remediation here.
   Document in docs/CLEANUP_MANIFEST.md under "Security — requires operator action":
   "tidal_tokens.json found in git history — requires manual git filter-repo
   by operator per OPS_RUNBOOK.md".

3. If .gitignore now covers it: commit the change.
   Commit: `chore(security): ensure tidal_tokens.json is gitignored`

═══════════════════════════════════════════════════════
PHASE E — STRUCTURAL BUGS: investigate only, do not fix
═══════════════════════════════════════════════════════

These are import/migration conflicts identified in the audit. Do NOT fix
them in this cleanup pass — they require separate targeted PRs.
Document findings only in docs/CLEANUP_MANIFEST.md.

E1. Migration 0007 collision in storage/migrations/:
    `ls tagslut/storage/migrations/0007*`
    Confirm both files exist. Check if MigrationRunner at
    tagslut/storage/migration_runner.py scans this directory and how
    it resolves filename collisions. Document finding.

E2. metadata/models.py vs metadata/models/ package:
    `ls tagslut/metadata/models*`
    Confirm both exist. Check which one is imported by other modules:
    `grep -r "from tagslut.metadata.models" tagslut/ tests/ --include="*.py"`
    `grep -r "from tagslut.metadata import models" tagslut/ tests/ --include="*.py"`
    Document all import sites and which target they resolve to.

E3. cli/scan.py + cli/track_hub_cli.py vs cli/commands/ duplicates:
    `ls tagslut/cli/scan.py tagslut/cli/track_hub_cli.py`
    `ls tagslut/cli/commands/scan.py tagslut/cli/commands/track_hub_cli.py`
    Check which are imported in tagslut/cli/main.py and tagslut/__main__.py.
    Document which copies are live and which are stale.

Commit manifest only:
  `docs(cleanup): document structural import conflicts from 2026-03-29 audit`

═══════════════════════════════════════════════════════
FINAL
═══════════════════════════════════════════════════════

  git status
  git push

Update docs/ROADMAP.md:
- Add under §7 (Repo housekeeping): "Supplement cleanup pass 2026-03-29: COMPLETE"
- List Phase E structural issues as open items needing targeted PRs.

Commit: `docs(roadmap): record 2026-03-29 cleanup supplement`
