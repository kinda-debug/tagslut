# tagslut — Agent Roadmap

<!-- Status: Active. Update as tasks complete or delegate assignments change. -->
<!-- Last updated: 2026-03-21 -->

This document maps all open work to the agent that should execute it.
Update it when tasks complete or priorities shift.

---

## Tool assignment logic

| Tool | Use for |
|---|---|
| **Codex** | Autonomous filesystem tasks: implement specs, write tests, refactor modules, run commands. Unlimited parallel tasks. Use for anything with a clear written prompt. |
| **Claude Code** | Judgment-critical work: architecture decisions, prompt authoring, audit, cross-cutting analysis. Rate-limit is real — reserve for tasks where reasoning quality matters. |
| **Copilot+** | Editor-native: inline completions, single-file edits, quick explanations of open files. Not for agentic tasks. |
| **Claude.ai (this)** | Strategic planning, prompt generation, review of agent output, decisions that require full context. |

---

## Current gate

**Phase 1 PR 9 (`fix/migration-0006`) is the blocker.**
PRs 10 (`fix/identity-service`) and 11 (`fix/backfill-v3`) cannot land until PR 9 merges.
See `docs/PHASE1_STATUS.md` for the full PR chain.

---

## 1 — Immediate (this session or next)

### 1.1 Resume/refresh fix → **Codex**
Prompt: `.github/prompts/resume-refresh-fix.prompt.md`
Three confirmed root causes in `tools/get-intake`. Fully specified. No judgment calls.
Status: prompt ready, not started.

### 1.2 Commit and push roadmap + remaining untracked files → **you**
```
git add docs/ROADMAP.md
git commit -m "chore: add agent roadmap"
git push
```

---

## 2 — Phase 1 PR chain → **Codex**

Work through the PR stack in order. Each has a narrow scope.
Use `tools/review/sync_phase1_prs.sh` to push without collapsing scope.

| PR | Task | Branch | Codex-ready? |
|---|---|---|---|
| 9 | Migration 0006 merge | `fix/migration-0006` | Yes — spec complete |
| 10 | Identity service | `fix/identity-service` | Yes — depends on 9 |
| 11 | Backfill command | `fix/backfill-v3` | Yes — depends on 10 |
| 12 | Identity merge | not started | Needs prompt |
| 13 | DJ candidate export | not started | Needs prompt |
| 14 | docs/AGENT update | not started | After 13 |
| 15 | Phase 2 seam | not started | Needs design first |

PRs 12–15 need prompts written in Claude.ai before Codex can execute them.
Do not ask Codex to design these — bring the spec, then delegate execution.

---

## 3 — DJ pipeline → **Codex** (with Claude.ai prompt authoring first)

### 3.1 DJ admission backfill
Run `tagslut dj backfill --db "$TAGSLUT_DB"` to populate `dj_admission` from
existing `mp3_asset` rows. Straightforward CLI invocation — Codex can script and verify.

### 3.2 DJ pipeline hardening
Prompt: `.github/prompts/dj-pipeline-hardening.prompt.md`
Enforce discipline on the old command surface, harden invariants, align
docs/help/tests. Codex-ready.

### 3.3 DJ workflow audit
Prompt: `.github/prompts/dj-workflow-audit.prompt.md`
Codex-ready.

---

## 4 — Lexicon → **Codex**

### 4.1 Lexicon reconcile
Prompt: `.github/prompts/lexicon-reconcile.prompt.md`
Codex-ready. 36% of identities (11,679) remain unmatched due to absence of
streaming IDs in Lexicon DB. Prompt covers the reconcile strategy.

### 4.2 Incremental Lexicon backfill after DB updates
Script: `python -m tagslut.dj.reconcile.lexicon_backfill --dry-run`
Codex can run this after any Lexicon DB update and commit the diff.

---

## 5 — Intake pipeline hardening → **Codex** (after 1.1 merges)

These depend on the resume/refresh fix landing first.

- Precheck inventory DJ link: wire `precheck_inventory_dj` correctly for
  `--dj`-only runs without `--m3u`. Partially addressed in 1.1.
- `intake_pretty_summary` accuracy: ensure counters reflect executed reality,
  not plan reality. Small targeted patch.
- Enrich scope in resume mode: verify `post_move_enrich_art.py` fires correctly
  after 1.1 fix. Write regression test.

---

## 6 — Open streams post → **Codex**

Prompt: `.github/prompts/open-streams-post-0010.prompt.md`
Write the publishable project update about the DJ pipeline cleanup.
Pure writing task with a clear source-reading list. Codex-ready.
No judgment calls — the prompt is fully specified.

---

## 7 — Repo housekeeping → **Codex**

### 7.1 Git history cleanup (do this soon — affects Copilot indexing)
Run `git filter-repo --strip-blobs-bigger-than 10M` to remove large historical
objects (postgres dump, fingerprint CSVs) from `.git/`. Shrinks repo from ~3 GB.
Force-push after: `git push --force origin dev`.

**Do this in a dedicated Codex session. Do not combine with other work.**

### 7.2 `.gitignore` validation after history cleanup
After filter-repo, verify `git status` is clean and no large files crept back.
Codex can script the check.

---

## 8 — Copilot+ scope (editor only — not agentic)

Copilot is for:
- Inline completions while editing `tools/get-intake`, `tagslut/dj/`, `tagslut/exec/`
- Quick explanations of unfamiliar code sections in VS Code chat
- Single-file edits where the change is obvious from context

Do not use Copilot for:
- Multi-file tasks (use Codex)
- Architecture decisions (use Claude.ai)
- Tasks requiring test runs to verify (use Codex or Claude Code)

---

## 9 — Reserved for Claude Code (rate-limit budget)

Use Claude Code only for:
- Authoring new Codex/Copilot prompts that require full codebase reasoning
- Reviewing Codex output that touches core identity model or DB schema
- Debugging failures that require reading multiple files and running commands interactively
- Any task where the spec itself is unclear and needs to be discovered

Everything else goes to Codex.

---

## Prompt files index

| File | Task | Agent |
|---|---|---|
| `resume-refresh-fix.prompt.md` | Fix `--resume` mode in `tools/get-intake` | Codex |
| `dj-pipeline-hardening.prompt.md` | Enforce DJ pipeline discipline | Codex |
| `dj-workflow-audit.prompt.md` | DJ workflow audit | Codex |
| `lexicon-reconcile.prompt.md` | Lexicon reconcile strategy | Codex |
| `open-streams-post-0010.prompt.md` | Write DJ pipeline post | Codex |

Prompts for Phase 1 PRs 12–15 and Phase 2 seam: **not yet written**.
Author these in Claude.ai before delegating to Codex.


---

## 10 — Clean slate: new DB, new config, fresh start → **you + Codex**

The current local setup has accumulated state: a Supabase epoch from February,
a SQLite DB at a hardcoded path, `.env` values pointing at volume paths that may
not survive a machine change, and config tied to the `tagtag` identity.

This section defines what a clean-slate setup looks like and what needs to happen
to get there. Do not migrate old state — start fresh.

### What "clean slate" means

- New SQLite DB initialized from scratch via migrations (do not copy `music_v3.db`)
- New Supabase local stack (`supabase db reset`) — no data carried over
- New `.env` from `.env.example` — fill in only what the current machine/setup needs
- New `beatportdl-config.yml` — do not copy from old setup
- Git identity confirmed as `kinda-debug` (already done)
- No references to old epoch paths (`EPOCH_2026-02-10_RELINK`, etc.)

### What to keep

- All code, migrations, and tests — these are the product
- `tagslut_db/` structure — but initialized fresh, not copied
- Volume paths in `.env` — update to reflect current machine mounts
- Supabase config in `supabase/config.toml` — already in repo, use as-is

### Steps → **you first, then Codex**

**You:**
1. Copy `.env.example` to `.env` and fill in paths for the current machine
2. Confirm volume mounts are correct (`$MASTER_LIBRARY`, `$DJ_LIBRARY`, staging roots)
3. Run `supabase db reset` to initialize a clean local Supabase stack
4. Update `.vscode/settings.json` SQLite path to point at the new DB location

**Codex:**
5. Run migrations from scratch: `poetry run tagslut db migrate` (or equivalent)
6. Verify schema matches expected state: `poetry run pytest tests/storage/ -v`
7. Run `tagslut dj backfill` against the new empty DB to establish baseline
8. Confirm `poetry run pytest tests/ -x -q` passes on the clean DB

### Gate

Do not run Lexicon backfill or any intake pipeline against the new DB until
steps 1–6 above are complete and the test suite passes clean.

### Note on `.vscode/settings.json`

Currently hardcoded to:
`/Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db`

Update this to the new DB path once the clean-slate DB is initialized.
This file is tracked in the repo — commit the updated path.


---

## 11 — Why the current DB cannot be trusted and what to do about it

### Root cause

The existing `music_v3.db` was built by ingesting file tags written by MusicBrainz
Picard. Picard writes directly to files and matches aggressively — including wrong
matches it treats as confident. When tagslut scanned those files, it took the tags
as ground truth and built the identity model on top of them.

The result: `track_identity` rows with Picard-authored ISRCs, artist names, and
album relationships that may be wrong, inconsistent, or duplicated. There is no
reliable way to audit which rows are trustworthy without re-deriving them from
scratch against a controlled source.

This is not a data hygiene problem. It is a provenance problem. The data cannot
be trusted because its origin cannot be verified.

### What this means in practice

- Do not migrate any identity rows from the old DB to the new one.
- Do not use old DB query results to pre-populate the new DB.
- Treat the old DB as read-only archaeology — useful for reference, not for import.
- Picard must never touch files that tagslut manages going forward. File tags
  are written by tagslut only, sourced from provider APIs (Beatport, TIDAL, MusicBrainz
  API — not Picard's local matching).

### The coexistence model: old tools, new DB

The code is fine. The data is not. This distinction makes coexistence straightforward:

- Keep running `tools/get-intake`, `tools/get`, all CLI commands — they all accept
  `--db` or read from `$TAGSLUT_DB`.
- Point `$TAGSLUT_DB` at the new empty DB instead of the old epoch.
- The old DB stays on disk at its current path, untouched, as a reference.
- Any lookup you want to do against old data: set `--db` explicitly to the old path.
  Never set it as the default.

Concretely in `.env`:

```
# New DB (active)
TAGSLUT_DB=/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db

# Old DB (reference only — never set as default)
# TAGSLUT_DB_LEGACY=/Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

### How to build a DB you can trust

The only source of truth is a controlled re-ingestion of your files through
the tagslut intake pipeline, with provider APIs as the metadata source.

**Rule: a track enters the DB exactly once, through `tools/get-intake`, with
a provider URL as the authoritative identity anchor. Never via Picard tags.**

Ingestion order that produces a trustworthy DB:

1. **Beatport purchases** — you have receipts, you have URLs. These are the
   highest-confidence identity anchors. Ingest via `tools/get --enrich <beatport-url>`.
   The ISRC and track ID come from the Beatport API, not from file tags.

2. **TIDAL verified matches** — cross-source confirmation. Where Beatport and
   TIDAL agree on ISRC, the identity is solid.

3. **MusicBrainz API** (not Picard) — for tracks not on Beatport. Query via
   the tagslut MusicBrainz provider, which fetches from the API with controlled
   matching logic. Not Picard's fuzzy local matching.

4. **Unresolved remainder** — tracks that cannot be anchored to any provider.
   These go into a separate bucket, clearly marked as unresolved, and are not
   promoted to `track_identity` until verified.

### What Picard is allowed to do going forward

Nothing inside the managed library. Picard can be used for:
- Pre-ingestion organization of completely untagged files before they enter
  the tagslut pipeline (as a one-time prep step, not ongoing)
- Files you explicitly want to keep outside tagslut management

Once a file is in `$MASTER_LIBRARY`, tagslut owns it. Picard does not touch it.

### Steps to initialize the new DB → **Codex**

```bash
# 1. Create the new DB directory
mkdir -p /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026

# 2. Initialize schema from migrations
TAGSLUT_DB=/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db \
  poetry run tagslut db migrate

# 3. Verify schema
TAGSLUT_DB=/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db \
  poetry run pytest tests/storage/ -v

# 4. Update .env to point at new DB
# 5. Update .vscode/settings.json SQLite path
```

Do not run any intake or backfill until step 3 passes clean.
