# tagslut — Agent Roadmap

<!-- Status: Active. Update as tasks complete or delegate assignments change. -->
<!-- Last updated: 2026-03-22 — DJ ffmpeg validation landed, docs updated, stop point recorded -->

This document maps all open work to the agent that should execute it.
Update it when tasks complete or priorities shift.

---

## ⚠ Global execution order — do not skip ahead

```text
1. Resume/refresh fix (§1)              ← COMPLETE
2. Ingestion provenance migration (§14) ← COMPLETE (commit bef5931)
3. Migration 0013 — five-tier CHECK (§16) ← COMPLETE (included in 0012)
4. Fresh DB initialization (§10)        ← COMPLETE (db + env + settings + storage tests)
5. Repo cleanup (§13)                   ← COMPLETE
6. Phase 1 PR chain (§2)               ← COMPLETE (PRs 9-15, all done)
7. DJ pipeline hardening (§3)          ← UNBLOCKED (Phase 1 complete)
```

Items 6 and 7 must not be started until items 1–4 are confirmed complete.

---

## Tool assignment logic

| Tool | Use for |
| --- | --- |
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

## 2 — Phase 1 PR chain → **Codex** ▶ IN PROGRESS (current top priority)

| PR | Task | Branch | Status |
| --- | --- | --- | --- |
| 9 | Migration 0006 merge | `fix/migration-0006` | COMPLETE (commit 5995983) |
| 10 | Identity service | `fix/identity-service` | COMPLETE (commit 767df22) |
| 11 | Backfill command | `fix/backfill-v3` | COMPLETE (commit 1e965b0) |
| 12 | Identity merge | `fix/identity-merge` | COMPLETE (195efc7, delivered via fix/migration-0006) |
| 13 | DJ candidate export | -- | COMPLETE (delivered in scripts/dj/export_candidates_v3.py, 8/8 tests) |
| 14 | docs/AGENT update | -- | COMPLETE (commit 8a0b00d) |
| 15 | Phase 2 seam | -- | COMPLETE (commit d992d20) |

PRs 13–15 need prompts authored in Claude.ai before Codex can execute them.
PR 12 prompt exists at `.github/prompts/phase1-pr12-identity-merge.prompt.md`.

---

## 3 — DJ pipeline → **Codex** ▶ ACTIVE FOLLOW-UP

Base pipeline work is complete (`eab34d3`, `d52fe27`) and the workflow audit is complete (`16ee5ca`).
The current stop point is a narrower hardening pass around Stage 2 transcode validation and
Stage 4 validation-gate behavior.

### 3.1 DJ pipeline hardening

Prompt: `.github/prompts/dj-pipeline-hardening.prompt.md`

### 3.2 DJ workflow audit ✅ COMPLETE (commit 16ee5ca)

Prompt: `.github/prompts/dj-workflow-audit.prompt.md`

### 3.3 FFmpeg output validation ✅ COMPLETE (commit de59b4f)

Prompt: `.github/prompts/dj-ffmpeg-validation.prompt.md`

Delivered:

- post-transcode MP3 validation in `tagslut/exec/transcoder.py`
- wizard failure surfacing in `tagslut/exec/dj_pool_wizard.py`
- focused tests in `tests/exec/test_mp3_build_ffmpeg_errors.py`
- follow-up cleanup commit `ea266a3` removed a duplicate helper definition
- doc commits `d234572` and `2d48601` recorded the operator-facing behavior

### 3.4 XML validation gate ⚠ REVIEW NEEDED

A separate DJ validation-state / XML preflight gate feature landed during the same work window.
It is broader than the FFmpeg-only prompt and should be treated as a separate review item before
further DJ hardening continues.

Affected files include:

- `tagslut/cli/commands/dj.py`
- `tagslut/dj/admission.py`
- `tagslut/dj/xml_emit.py`
- `tagslut/storage/v3/migrations/0014_dj_validation_state.py`
- `tagslut/storage/v3/schema.py`
- `tests/exec/test_dj_xml_preflight_validation.py`

### 3.5 DJ admission backfill

⚠ No-op against empty DB. Run only after first successful ingestion into fresh DB.

---

## 4 — Lexicon → **Codex**

### 4.1 Lexicon reconcile

Prompt: `.github/prompts/lexicon-reconcile.prompt.md`
36% of identities (11,679) unmatched — no streaming-ID fallback in Lexicon DB.

### 4.2 Incremental backfill

`python -m tagslut.dj.reconcile.lexicon_backfill --dry-run` after any Lexicon DB update.

---

## 5 — Intake pipeline hardening → **Codex** ▶ UNBLOCKED

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

### 7.2 Script and docs cleanup: COMPLETE (2026-03-22)

Prompt: `.github/prompts/repo-cleanup.prompt.md`
Cleanup manifest: `docs/CLEANUP_MANIFEST.md`
Follow-up: residual `artifacts/*.log` files were relocated to the LEGACY epoch directory.

---

## 8 — Copilot+ scope (editor only)

Inline completions, quick chat about open files in VS Code. Not for agentic tasks.

---

## 9 — Reserved for Claude Code (rate-limit budget)

Prompts for PRs 12–15, reviewing Codex output on identity model changes,
debugging where the problem itself is unclear.

---

## 10 — Clean slate: new DB, new config → **you + Codex**

✅ COMPLETE (2026-03-22)

Prerequisites §14 and §16 are landed.

DB paths:
  LEGACY: `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db`
  FRESH:  `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`

Completion evidence:

- `.env` created from `.env.example`
- fresh DB created at FRESH path
- `.vscode/settings.json` updated with `music (fresh)` and `music (legacy — read-only)`
- `poetry run pytest tests/storage/ -v` passed (`139 passed`)

Gate status: satisfied. Phase 1 PR chain may proceed.

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

## 13 — Script, docs, log cleanup: COMPLETE (2026-03-22)

Cleanup pass complete. See `docs/CLEANUP_MANIFEST.md` for deleted, archived,
and intentionally retained files.

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
| --- | --- | --- | --- |
| `resume-refresh-fix.prompt.md` | Fix `--resume` in `tools/get-intake` | Codex | COMPLETE |
| `repo-cleanup.prompt.md` | Archive dead scripts and stale docs | Codex | Ready |
| `dj-pipeline-hardening.prompt.md` | DJ pipeline discipline | Codex | Blocked (Phase 1) |
| `dj-workflow-audit.prompt.md` | DJ workflow audit | Codex | Blocked (Phase 1) |
| `lexicon-reconcile.prompt.md` | Lexicon reconcile strategy | Codex | Ready |
| `open-streams-post-0010.prompt.md` | Write DJ pipeline post | Codex | Ready |
| `postman-api-optimize.prompt.md` | Beatport API collection | Postman | COMPLETE |

Prompts for Phase 1 PRs 12–15 and Phase 2 seam: not yet written.
Author in Claude.ai before delegating to Codex.

---

## 18 — Credential management consolidation → **Claude Code + Codex**

Audit: `docs/CREDENTIAL_MANAGEMENT_AUDIT.md` (see full audit report)
Target doc: `docs/CREDENTIAL_MANAGEMENT.md` (to be written)

### Problem summary

Two credential systems operating in parallel with undocumented precedence:

- **System A** (legacy): `env_exports.sh` shell pattern — archived but still
  referenced by 3 harvest scripts and 1 Python docstring
- **System B** (modern): `TokenManager` + `~/.config/tagslut/tokens.json` —
  correct approach but incompletely adopted
- **System C** (Postman): environment vars in Postman collection — integration
  testing only, not a source of truth

Critical issue: `beatport.py` checks `os.getenv("BEATPORT_ACCESS_TOKEN")` FIRST,
meaning a stale env var silently wins over a fresh token in tokens.json.
No operator documentation of this precedence exists.

### Not on the critical path

This does not block migrations 0012/0013, fresh DB init, or Phase 1 PRs.
The intake pipeline is functional with the existing setup.
Do not start this until the migration chain is complete.

### Phase 1 — Document + fix precedence → **Codex** (after §14 + §16 land)

1. Write `docs/CREDENTIAL_MANAGEMENT.md` — tokens.json as single source of truth,
   per-provider setup instructions, Postman sync note
2. Fix precedence in `beatport.py` — tokens.json first, env var fallback with warning log
3. Update `.env.example` to point at `~/.config/tagslut/tokens.json`
4. Add `tagslut token-get <provider>` CLI command for shell script use

Commit: `feat(auth): establish tokens.json precedence, add token-get command`

### Phase 2 — Migrate shell scripts → **Codex** (after Phase 1)

Replace env var reads in harvest scripts with:

```bash
BEATPORT_ACCESS_TOKEN=$(tagslut token-get beatport)
```

Scripts to update:

- `tagslut/metadata/beatport_harvest_catalog_track.sh`
- `tagslut/metadata/beatport_harvest_my_tracks.sh`
- `tools/beatport_import_my_tracks.py` (docstring + credential read)

Commit: `fix(auth): migrate harvest scripts to token-get command`

### Phase 3 — Beatport token refresh → **Claude Code design + Codex impl**

Beatport access tokens expire after 1 hour with no documented refresh grant.
Research required before implementation:

- Does Beatport OAuth 2.0 support refresh tokens?
- If not, implement expiry detection + prompt for re-paste in TokenManager
- Add expiry warning to `tagslut auth status`

### Open questions (operator decisions required before Phase 1)

1. Should `BEATPORT_ACCESS_TOKEN` env var remain supported as a fallback,
   or be removed entirely? (Postman and CI may depend on it)
2. Should Postman token sync be automated (`tagslut postman sync`) or remain manual?
3. Qobuz stores email + password_md5 in tokens.json — acceptable or switch to API key?

### Estimated effort

Phase 1: 2–3 hours (Codex, well-scoped)
Phase 2: 1–2 hours (Codex, mechanical)
Phase 3: unknown (depends on Beatport refresh research)
