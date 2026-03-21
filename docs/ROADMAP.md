# tagslut — Agent Roadmap

<!-- Status: Active. Update as tasks complete or delegate assignments change. -->
<!-- Last updated: 2026-03-21 — revised after external review -->

This document maps all open work to the agent that should execute it.
Update it when tasks complete or priorities shift.

---

## ⚠ Global execution order — do not skip ahead

```
1. Resume/refresh fix (§1)         ← unblocks daily intake NOW
2. Ingestion provenance migration (§14)  ← prerequisite for fresh DB
3. Fresh DB initialization (§10)   ← prerequisite for clean-slate ingestion
4. Repo cleanup (§13)              ← parallel, no dependencies
5. Phase 1 PR chain (§2)          ← BLOCKED until items 1–3 complete
6. DJ pipeline hardening (§3)     ← after Phase 1
```

Items 5 and 6 must not be started until items 1–3 are confirmed complete.

---

## Tool assignment logic

| Tool | Use for |
|---|---|
| **Codex** | Autonomous implementation — all tasks with a prompt file in `.github/prompts/`. Run from repo root. Never ask Codex to design; give it a spec first. |
| **Claude Code** | Judgment-critical: prompt authoring, architecture decisions, cross-cutting audit, debugging where the problem is unclear. Rate-limited — use sparingly. |
| **Copilot+** | Editor inline completions and single-file chat only. Not for agentic tasks. |
| **Claude.ai** | Strategic planning, prompt generation, review of agent output. |

---

## Testing policy

Default: targeted pytest only.
  `poetry run pytest tests/<specific_module> -v`

Exception: a full suite run (`poetry run pytest tests/ -x -q`) is permitted
only as a final gate immediately before merging a PR. Not during implementation.
Any agent that runs the full suite during implementation is violating this policy.

---

## 1 — Immediate → **Codex**

### 1.1 Resume/refresh fix
Prompt: `.github/prompts/resume-refresh-fix.prompt.md`
Three confirmed root causes in `tools/get-intake`. Fully specified.
Status: prompt ready, not started.

---

## 2 — Phase 1 PR chain → **Codex** ⛔ BLOCKED until §1 + §14 + §10 complete

Work through the PR stack in order. Each has a narrow scope.
Use `tools/review/sync_phase1_prs.sh` to push without collapsing scope.

| PR | Task | Branch | Status |
|---|---|---|---|
| 9 | Migration 0006 merge | `fix/migration-0006` | IN PROGRESS — current gate |
| 10 | Identity service | `fix/identity-service` | READY — depends on 9 |
| 11 | Backfill command | `fix/backfill-v3` | READY — depends on 10 |
| 12 | Identity merge | not started | Needs prompt |
| 13 | DJ candidate export | not started | Needs prompt |
| 14 | docs/AGENT update | not started | After 13 |
| 15 | Phase 2 seam | not started | Needs design first |

PRs 12–15 need prompts authored in Claude.ai before Codex can execute them.

---

## 3 — DJ pipeline → **Codex** (prompts ready) ⛔ BLOCKED until Phase 1 lands

### 3.1 DJ pipeline hardening
Prompt: `.github/prompts/dj-pipeline-hardening.prompt.md`

### 3.2 DJ workflow audit
Prompt: `.github/prompts/dj-workflow-audit.prompt.md`

### 3.3 DJ admission backfill
⚠ No-op against an empty DB. Run only after first successful ingestion into fresh DB.
Command: `tagslut dj backfill --db "$TAGSLUT_DB"`
This is a post-ingestion sanity check, not part of fresh DB initialization.

---

## 4 — Lexicon → **Codex**

### 4.1 Lexicon reconcile
Prompt: `.github/prompts/lexicon-reconcile.prompt.md`
Status: prompt exists in repo, not yet in bundle — add to next bundle refresh.
36% of identities (11,679) unmatched due to absence of streaming IDs in Lexicon DB.

### 4.2 Incremental Lexicon backfill after DB updates
`python -m tagslut.dj.reconcile.lexicon_backfill --dry-run`
Run after any Lexicon DB update; commit the diff.

---

## 5 — Intake pipeline hardening → **Codex** (after §1 merges)

- `precheck_inventory_dj` fallback for `--dj`-only runs without `--m3u`
- `intake_pretty_summary` counter accuracy
- Enrich scope regression test after resume fix lands
- Log redirect: `POST_MOVE_LOG` default path should write to epoch dir, not `artifacts/`

---

## 6 — Open streams post → **Codex**

Prompt: `.github/prompts/open-streams-post-0010.prompt.md`
Pure writing task with a defined source-reading list. No judgment calls.

---

## 7 — Repo housekeeping → **Codex**

### 7.1 Git history cleanup ⚠ OPERATOR-ONLY — do not delegate to any agent

NOT a standard Codex task. This is an exceptional maintenance procedure
that requires a force-push and must be executed manually by the operator.
Full runbook: `docs/OPS_RUNBOOK.md` (to be written).

Summary of what it involves:
- `git filter-repo --strip-blobs-bigger-than 10M` to remove large historical objects
- `git push --force origin dev`
- Verify Copilot reindexes after cleanup

Do not put this in a Codex prompt. Do not ask any agent to run it.

### 7.2 Script and docs cleanup → **Codex**
Prompt: `.github/prompts/repo-cleanup.prompt.md`
Status: prompt ready, not started.

Manual cleanup already completed (2026-03-21):
- Deleted: redundant March 4 DB backups (~750 MB recovered)
- Deleted: ~450+ write-test markers across epochs
- Moved: `artifacts/*.log` → `LEGACY_2026-03-04_PICARD/`
- Deleted: sensitive untracked files (auth, tokens, HAR, API dumps, MCP test files)
- Deleted: empty placeholder files
- Renamed: EPOCH_2026-03-04 → LEGACY_2026-03-04_PICARD
- Backed up: `music_v3.bak.20260321.db`
- Checkpointed: `lexicondj_update.db` WAL on /Volumes/MUSIC

Remaining for Codex: scripts/, docs/, tools/ triage — read-then-decide, not mass delete.

---

## 8 — Copilot+ scope (editor only)

Copilot is for: inline completions, quick chat about open files in VS Code.
Not for: multi-file tasks, architecture decisions, test-verified changes.

---

## 9 — Reserved for Claude Code (rate-limit budget)

Use only for: authoring prompts for PRs 12–15, reviewing Codex output on
identity model changes, debugging where the problem itself is unclear.
Everything else goes to Codex.

---

## 10 — Clean slate: new DB, new config → **you + Codex**
⛔ Prerequisite: §14 (provenance migration) must be written and committed first.

### What "clean slate" means
- New SQLite DB initialized from migrations (do not copy `music_v3.db`)
- New Supabase local stack (`supabase db reset`) — no data carried over
- New `.env` from `.env.example`
- New `beatportdl-config.yml`
- No references to legacy epoch paths

### DB paths (current machine)
```
LEGACY (read-only):
  /Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db

FRESH (target):
  /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db
  (does not exist yet — initialize from migrations)
```

### Steps
You: copy `.env.example` → `.env`, set volume paths, run `supabase db reset`
Codex: run migrations, verify schema, run `poetry run pytest tests/storage/ -v`

Gate: do not run any intake or DJ admission backfill until storage tests pass clean.

### .vscode/settings.json
Currently hardcoded to legacy path. Update to:
- `music (legacy)` → `LEGACY_2026-03-04_PICARD/music_v3.db` (read-only label)
- `music (fresh)` → `FRESH_2026/music_v3.db`
Commit after fresh DB is initialized.

---

## 11 — Why the legacy DB cannot be trusted

Root cause: the existing `music_v3.db` was built by ingesting file tags
written by MusicBrainz Picard. Picard writes directly to files and matches
aggressively — including wrong matches it treats as confident. The identity
model is built on top of whatever Picard decided.

This is a provenance problem, not a data hygiene problem. The data cannot
be trusted because its origin cannot be verified.

Rules:
- Do not migrate identity rows from legacy DB to fresh DB
- Do not use legacy DB query results to pre-populate the fresh DB
- Picard must never touch files that tagslut manages going forward
- The legacy DB is read-only archaeology — useful for cross-reference, not import

Coexistence: all tools accept `--db`. Point `$TAGSLUT_DB` at the fresh DB.
For legacy lookups: `--db /path/to/LEGACY_2026-03-04_PICARD/music_v3.db` explicitly.

---

## 12 — DB and backup audit: COMPLETE (2026-03-21)

All cleanup actions from this section have been executed. Summary:

SAD volume epochs (all legacy, read-only):
  EPOCH_2026-02-08   — music.db (v1) + classify-v2 snapshot
  EPOCH_2026-02-10_RELINK — music.db + music_v2.db (WAL was dirty, now clean)
  EPOCH_2026-02-28   — music.db + music_v2.db

Active epoch renamed:
  EPOCH_2026-03-04 → LEGACY_2026-03-04_PICARD

Backup taken:
  LEGACY_2026-03-04_PICARD/music_v3.bak.20260321.db

Deleted (LEGACY_2026-03-04_PICARD):
  music_v3.bak.20260304_162925.db
  music_v3.bak.20260304_162657.db
  music_v3.bak.20260304_162428.db
  ~250 .tagslut_write_test_* markers

Deleted (SAD epochs):
  ~200 .dedupe_write_test_* and .tagslut_write_test_* markers

lexicondj_update.db WAL checkpointed and truncated.

Backup policy going forward: one backup per significant session,
named `music_v3.bak.YYYYMMDD.db`. Keep last two. Delete older ones manually.

---

## 13 — Script, docs, log cleanup: PARTIAL (2026-03-21)

Manual phase complete (see §7.2 above for what was done).
Codex phase pending: `.github/prompts/repo-cleanup.prompt.md`

Log management policy going forward:
- Logs write to epoch directory, not into repo `artifacts/`
- Requires one-line patch to `tools/get-intake` (`POST_MOVE_LOG` default path)
- Add to §5 (intake pipeline hardening) once resume fix lands

---

## 14 — Ingestion provenance migration → **Codex** ⛔ PREREQUISITE for §10

Spec: `docs/INGESTION_PROVENANCE.md`
Must be the first migration applied to the fresh DB.
Must land before any clean-slate ingestion runs.

Four columns added to `track_identity`:
  `ingested_at`           ISO 8601 UTC, set once, never updated
  `ingestion_method`      controlled vocabulary
  `ingestion_source`      specific evidence string
  `ingestion_confidence`  verified | high | uncertain | legacy

Codex task:
1. Write migration file in `supabase/migrations/` (SQL in `INGESTION_PROVENANCE.md`)
2. Add NOT NULL constraints to `tagslut/storage/v3/schema.py`
3. Update `tools/get-intake` to write all four fields on every insert
4. Add test: insert without `ingestion_method` must raise integrity error
5. Update `docs/DB_V3_SCHEMA.md`

Commit: `feat(schema): add ingestion provenance columns to track_identity`

---

## Prompt files index

| File | Task | Agent | Status |
|---|---|---|---|
| `resume-refresh-fix.prompt.md` | Fix `--resume` in `tools/get-intake` | Codex | Ready |
| `repo-cleanup.prompt.md` | Archive dead scripts and stale docs | Codex | Ready |
| `dj-pipeline-hardening.prompt.md` | Enforce DJ pipeline discipline | Codex | Blocked (Phase 1) |
| `dj-workflow-audit.prompt.md` | DJ workflow audit | Codex | Blocked (Phase 1) |
| `lexicon-reconcile.prompt.md` | Lexicon reconcile strategy | Codex | Ready — add to bundle |
| `open-streams-post-0010.prompt.md` | Write DJ pipeline post | Codex | Ready |

Prompts for Phase 1 PRs 12–15 and Phase 2 seam: not yet written.
Author in Claude.ai before delegating to Codex.
