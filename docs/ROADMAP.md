# tagslut — Agent Roadmap

<!-- Status: Active. Update as tasks complete or delegate assignments change. -->
<!-- Last updated: 2026-03-21 — end of session -->

This document maps all open work to the agent that should execute it.
Update it when tasks complete or priorities shift.

---

## ⚠ Global execution order — do not skip ahead

```
1. Resume/refresh fix (§1)              ← COMPLETE
2. Ingestion provenance migration (§14) ← prerequisite for fresh DB
3. Migration 0013 — five-tier CHECK (§16) ← prerequisite for Track B processing
4. Fresh DB initialization (§10)        ← prerequisite for clean-slate ingestion
5. Repo cleanup (§13)                   ← parallel, no dependencies
6. Phase 1 PR chain (§2)               ← BLOCKED until items 1–4 complete
7. DJ pipeline hardening (§3)          ← after Phase 1
```

Items 6 and 7 must not be started until items 1–4 are confirmed complete.

---

## Tool assignment logic

| Tool | Use for |
|---|---|
| **Codex** | Autonomous implementation — all tasks with a prompt file in `.github/prompts/`. Run from repo root. Never ask Codex to design; give it a spec first. |
| **Claude Code** | Judgment-critical: prompt authoring, architecture decisions, cross-cutting audit, debugging where the problem is unclear. Rate-limited — use sparingly. |
| **Copilot+** | Editor inline completions and single-file chat only. Not for agentic tasks. |
| **Claude.ai** | Strategic planning, prompt generation, review of agent output. |

## Delegation protocol — who does what, and when

Every delegated task must start with:
- **Read first:** the single file that must be read before anything else
- **Verify before editing:** the exact command, failing test, or behavior to confirm
- **Allowed verification:** targeted pytest only, unless full-suite exception is stated
- **Stop and escalate if:** the condition that makes the task no longer implementation-only
- **Done when:** the observable completion condition

### 1. Codex = default executor
Use when a prompt exists, spec is written, behavior and acceptance criteria are clear.
Responsibilities: smallest reversible patch, targeted verification, conventional commits.

### 2. Claude Code = ambiguity resolver, prompt author, reviewer
Use when the problem is unclear, change is architecture-sensitive, or identity/schema
invariants may be affected. Should not become the default implementer.

### 3. Copilot+ = editor-only
Inline completions, explanation of open files, tiny mechanical edits. Nothing else.

### 4. Operator-only lane
Never delegate: `git push --force`, `git filter-repo`, direct DB file modification,
writes to mounted library volumes, any step marked operator-only.

### 5. Escalation rules
Copilot+ → Codex: change expands beyond one file, verification requires commands.
Codex → Claude Code: spec underspecified, root cause differs, identity/storage affected.
Any agent → operator: force-push, unmounted volume, real DB or library path required.

---

## Testing policy

Default: `poetry run pytest tests/<specific_module> -v`
Exception: full suite (`poetry run pytest tests/ -x -q`) only as final gate before
merging a PR. Never during implementation.

---

## 1 — Resume/refresh fix: COMPLETE (2026-03-21)

All three root causes verified implemented and passing.
`poetry run pytest tests/exec/test_resume_refresh.py -v` — 7/7 PASSED
Commits: 730d2b1, 2fb2a50, 3f3f37d, bf3df38

---

## 2 — Phase 1 PR chain → **Codex** ⛔ BLOCKED until §14 + §16 + §10 complete

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

## 3 — DJ pipeline → **Codex** ⛔ BLOCKED until Phase 1 lands

### 3.1 DJ pipeline hardening
Prompt: `.github/prompts/dj-pipeline-hardening.prompt.md`

### 3.2 DJ workflow audit
Prompt: `.github/prompts/dj-workflow-audit.prompt.md`

### 3.3 DJ admission backfill
⚠ No-op against empty DB. Run only after first successful ingestion into fresh DB.

---

## 4 — Lexicon → **Codex**

### 4.1 Lexicon reconcile
Prompt: `.github/prompts/lexicon-reconcile.prompt.md`
36% of identities (11,679) unmatched — no streaming-ID fallback in Lexicon DB.

### 4.2 Incremental backfill
`python -m tagslut.dj.reconcile.lexicon_backfill --dry-run` after any Lexicon DB update.

---

## 5 — Intake pipeline hardening → **Codex** (after §1 merged)

- `precheck_inventory_dj` fallback for `--dj`-only runs without `--m3u`
- `intake_pretty_summary` counter accuracy
- Log redirect: `POST_MOVE_LOG` default path → epoch dir, not `artifacts/`

---

## 6 — Open streams post → **Codex**
Prompt: `.github/prompts/open-streams-post-0010.prompt.md`

---

## 7 — Repo housekeeping

### 7.1 Git history cleanup ⚠ OPERATOR-ONLY
`git filter-repo --strip-blobs-bigger-than 10M` + `git push --force origin dev`
Never delegate. Full runbook: `docs/OPS_RUNBOOK.md` (to be written).

### 7.2 Script and docs cleanup → **Codex**
Prompt: `.github/prompts/repo-cleanup.prompt.md`
Manual phase complete (2026-03-21). Codex phase pending.

---

## 8 — Copilot+ scope (editor only)
Inline completions, quick chat about open files in VS Code. Not for agentic tasks.

---

## 9 — Reserved for Claude Code (rate-limit budget)
Prompts for PRs 12–15, reviewing Codex output on identity model changes,
debugging where the problem itself is unclear.

---

## 10 — Clean slate: new DB, new config → **you + Codex**
⛔ Prerequisites: §14 (provenance migration) and §16 (migration 0013) must land first.

DB paths:
  LEGACY: `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db`
  FRESH:  `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db` (not yet created)

Steps:
- You: copy `.env.example` → `.env`, confirm volume paths, `supabase db reset`
- Codex: run migrations, verify schema, `poetry run pytest tests/storage/ -v`
- Gate: no intake or DJ admission backfill until storage tests pass clean

`.vscode/settings.json` needs updating after fresh DB is initialized:
  `music (legacy)` → LEGACY path (read-only label)
  `music (fresh)`  → FRESH path

---

## 11 — Why the legacy DB cannot be trusted

Root cause: identity model built on MusicBrainz Picard-written tags. Picard matches
aggressively and the origin of every identity is unverifiable.

Rules:
- Do not migrate identity rows from legacy DB to fresh DB
- Picard must never touch files tagslut manages going forward
- Legacy DB is read-only archaeology only — use `--db LEGACY_PATH` explicitly

---

## 12 — DB and backup audit: COMPLETE (2026-03-21)

Epoch renamed EPOCH_2026-03-04 → LEGACY_2026-03-04_PICARD. Redundant backups deleted.
Write-test markers deleted (~450+). Backup taken: `music_v3.bak.20260321.db`.
Artifacts swept to `/Volumes/SAD/tagslut_artifacts_archive/` (182 MB).
`lexicondj_update.db` WAL checkpointed.

Backup policy: one backup per significant session, named `music_v3.bak.YYYYMMDD.db`.
Keep last two. Delete older manually.

---

## 13 — Script, docs, log cleanup: PARTIAL (2026-03-21)

Manual phase complete. Codex phase pending: `.github/prompts/repo-cleanup.prompt.md`

Log policy: logs write to epoch directory, not `artifacts/`. Requires one-line patch
to `tools/get-intake` (`POST_MOVE_LOG` default path) — add to §5 after resume fix lands.

---

## 14 — Ingestion provenance migration → **Codex** ⛔ PREREQUISITE for §10

Spec: `docs/INGESTION_PROVENANCE.md` + `docs/MULTI_PROVIDER_ID_POLICY.md`

Four columns on `track_identity`: `ingested_at`, `ingestion_method`,
`ingestion_source`, `ingestion_confidence` — all NOT NULL, no DEFAULT.

Confidence vocabulary (five-tier — see §16 for CHECK constraint):
  `verified` | `corroborated` | `high` | `uncertain` | `legacy`

Method vocabulary includes: `provider_api`, `isrc_lookup`, `fingerprint_match`,
`fuzzy_text_match`, `picard_tag`, `manual`, `migration`, `multi_provider_reconcile`

Codex task:
1. Write `tagslut/storage/v3/migrations/0012_ingestion_provenance.py`
2. Write `supabase/migrations/20260322000000_add_ingestion_provenance.sql`
3. Add NOT NULL to `tagslut/storage/v3/schema.py`
4. Update all five `track_identity` insert surfaces
5. Add enforcement trigger in both schema.py and migration 0012
6. Update ~25 test fixtures (use conftest.py helper to reduce churn)
7. Update `docs/DB_V3_SCHEMA.md`

Commit: `feat(schema): add ingestion provenance columns to track_identity`

---

## 15 — TIDAL OAuth refactor: COMPLETE (2026-03-21)

Commit: `3a3595c`. Global mutable state removed, monotonic clock, private naming,
docstring restored. No behaviour changes. No further work needed.

---

## 16 — Migration 0013: five-tier confidence CHECK → **Codex** ⛔ PREREQUISITE for §10

Spec: `docs/MULTI_PROVIDER_ID_POLICY.md` §schema-implication

Update `ingestion_confidence` CHECK constraint to allow five values:
  `verified` | `corroborated` | `high` | `uncertain` | `legacy`

Add `'multi_provider_reconcile'` to `ingestion_method` controlled vocabulary.

Must land after migration 0012 (§14) and before fresh DB initialization (§10).

Codex task:
1. Write `tagslut/storage/v3/migrations/0013_confidence_tier_update.py`
2. Update CHECK constraint in `tagslut/storage/v3/schema.py`
3. Update `supabase/migrations/` with corresponding Postgres migration
4. Update `docs/DB_V3_SCHEMA.md` — confidence and method vocabulary tables

Commit: `feat(schema): five-tier ingestion_confidence CHECK + multi_provider_reconcile method`

---

## 17 — Postman API collection: COMPLETE (2026-03-21)

All agent tasks done. Final commit: `14c9e29`.

Completed: collection cleanup, `base_url` + token expiry, ISRC auth resolution,
Track by ID field validation, Identity Verification chain (5a Beatport → 5b TIDAL
→ 5c Spotify), Validation Run folder (6a → 6b → 5a → 5b → 5c), token guard.

Remaining operator task: run Validation Run in Collection Runner with live TIDAL token.
Pass: `5b` + `5c` both log `CORROBORATED`. Then open PR `dev → main`.
Prompt: `.github/prompts/postman-api-optimize.prompt.md` (status: COMPLETE)

---

## Prompt files index

| File | Task | Agent | Status |
|---|---|---|---|
| `resume-refresh-fix.prompt.md` | Fix `--resume` in `tools/get-intake` | Codex | COMPLETE |
| `repo-cleanup.prompt.md` | Archive dead scripts and stale docs | Codex | Ready |
| `dj-pipeline-hardening.prompt.md` | DJ pipeline discipline | Codex | Blocked (Phase 1) |
| `dj-workflow-audit.prompt.md` | DJ workflow audit | Codex | Blocked (Phase 1) |
| `lexicon-reconcile.prompt.md` | Lexicon reconcile strategy | Codex | Ready |
| `open-streams-post-0010.prompt.md` | Write DJ pipeline post | Codex | Ready |
| `postman-api-optimize.prompt.md` | Beatport API collection | Postman | COMPLETE |

Prompts for Phase 1 PRs 12–15 and Phase 2 seam: not yet written.
Author in Claude.ai before delegating to Codex.
