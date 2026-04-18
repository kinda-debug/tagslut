# tagslut — Agent Roadmap

<!-- Status: Active. Update as tasks complete or delegate assignments change. -->
<!-- Last updated: 2026-04-02 — §20/§21/§23 COMPLETE; Qobuz metadata and ReccoBeats audio features live; DJ pool M3U model active. -->
<!-- Active action sequencing has moved to docs/archive/ACTION_PLAN.md -->
<!-- This file remains the agent contract reference and historical record. -->

This document maps all open work to the agent that should execute it.
Update it when tasks complete or priorities shift.

---

## ⚠ Global execution order — do not skip ahead

```text
1. Resume/refresh fix (§1)              ← COMPLETE
2. Ingestion provenance migration (§14) ← COMPLETE (commit bef5931)
3. Migration 0013 — five-tier CHECK (§16) ← COMPLETE (explicit SQLite migration)
4. Fresh DB initialization (§10)        ← COMPLETE (db + env + settings + storage tests)
5. Repo cleanup (§13)                   ← COMPLETE
6. Phase 1 PR chain (§2)               ← COMPLETE (PRs 9-15, all done)
7. TIDAL provider migration (§19)       ← COMPLETE (commit 50062ea)
8. Intake pipeline hardening (§5)       ← COMPLETE (commits 8590e75, d0c42e6)
9. DJ pipeline hardening (§3)          ← UNBLOCKED (open review items remain)
10. Token bridge + download strategy (§20, §21) ← COMPLETE (2026-04-01)
11. Provider architecture + Qobuz metadata (§23)  ← COMPLETE (2026-04-01)
12. DJ pool M3U model — replace 4-stage pipeline  ← COMPLETE (2026-04-01)
13. beatportdl restore as explicit download path  ← COMPLETE (2026-04-01)
14. ReccoBeats audio-features provider activation  ← COMPLETE (2026-04-02)
```

Items must not be skipped; each depends on the prior gate being confirmed complete.

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

## 2 — Phase 1 PR chain: COMPLETE (2026-03-25)

| PR | Task | Branch | Status |
| --- | --- | --- | --- |
| 9 | Migration 0006 merge | `fix/migration-0006` | COMPLETE (commit 5995983) |
| 10 | Identity service | `fix/identity-service` | COMPLETE (commit 767df22) |
| 11 | Backfill command | `fix/backfill-v3` | COMPLETE (commit 1e965b0) |
| 12 | Identity merge | `fix/identity-merge` | COMPLETE (195efc7, delivered via fix/migration-0006) |
| 13 | DJ candidate export | -- | COMPLETE (delivered in scripts/dj/export_candidates_v3.py, 8/8 tests) |
| 14 | docs/AGENT update | -- | COMPLETE (commit 8a0b00d) |
| 15 | Phase 2 seam | -- | COMPLETE (commit d992d20) |

---

## 3 — DJ pipeline → **Codex**

Base pipeline work is complete (`eab34d3`, `d52fe27`) and the workflow audit is complete (`16ee5ca`).

### 3.1 DJ pipeline hardening ✅ COMPLETE

### 3.2 DJ workflow audit ✅ COMPLETE (commit 16ee5ca)

### 3.3 FFmpeg output validation ✅ COMPLETE (commit de59b4f)

Delivered:
- post-transcode MP3 validation in `tagslut/exec/transcoder.py`
- wizard failure surfacing in `tagslut/exec/dj_pool_wizard.py`
- focused tests in `tests/exec/test_mp3_build_ffmpeg_errors.py`

### 3.4 XML validation gate ✅ COMPLETE (b9576ab)

Three fixes applied:
1. `compute_dj_state_hash` widened — joins `mp3_asset`, includes `path` + `status`
2. Migration 0015: `issue_count` + `summary` added to `dj_validation_state`
3. `DjValidationGateError` sentinel class; `EMIT_BLOCKING_ISSUE_KINDS` named constant
   `INACTIVE_PLAYLIST_MEMBER` excluded by policy — playlists are advisory.
19/19 tests passing.

### 3.5 DJ admission backfill — pipeline-state-dependent

Not a one-time task. Re-run `dj backfill --dry-run` after any significant intake batch.

---

## 4 — Lexicon → **Codex**

### 4.1 Lexicon reconcile

Prompt: `.github/prompts/lexicon-reconcile.prompt.md`
Implemented first slice: `tagslut lexicon import` and `import-playlists`
accept Lexicon `main.db` or backup ZIP snapshots, prefer `Track.locationUnique`
for path matching, and preserve Lexicon provenance in
`track_identity.canonical_payload_json`.

### 4.2 Incremental backfill

`python -m tagslut.dj.reconcile.lexicon_backfill --lex <backup.zip|main.db> --dry-run`
after any Lexicon DB update.

---

## 5 — Intake pipeline hardening: ✅ COMPLETE (2026-03-26)

All five fixes applied and on `dev`:

- Fix 1 (POST_MOVE_LOG → epoch dir): `tools/get-intake` lines 2871–2875
- Fix 2 (planned counters): `tagslut/exec/intake_pretty_summary.py` lines 111, 164–166
- Fix 3 (DJ_ROOT/DJ_M3U_DIR guard): `tools/get-intake` lines 1955, 1958
- Fix 4 (stamp-aware artifact selection): `get_intake_console.py` — derives run stamp from
  raw log filename; prevents stale precheck CSVs from prior runs being attached to current report
- Fix 5 (Tidal auth-failure fallback): `tools/get-intake` — detects `tidal_token_missing`;
  with `--force-download` bypasses precheck and falls back to direct Tidal download;
  without `--force-download` fails with explicit re-auth instructions

Commits: `8590e75`, `d0c42e6`

---

## 6 — Open streams post → **Codex**

Prompt: `.github/prompts/open-streams-post-0010.prompt.md`

---

## 7 — Repo housekeeping

### 7.1 Git history cleanup ⚠ OPERATOR-ONLY

`git filter-repo --strip-blobs-bigger-than 10M` + `git push --force origin dev`
Never delegate. Full runbook: `docs/OPS_RUNBOOK.md` (to be written).

### 7.2 Script and docs cleanup: COMPLETE (2026-03-22)

### 7.3 Supplement cleanup pass: COMPLETE (2026-03-29 + 2026-03-30)

Supplement cleanup pass 2026-03-29: COMPLETE

Structural audit (2026-03-30):
- `models.py` vs `models/` package: not a conflict — intentional shim. No action needed.
- `cli/scan.py` + `cli/track_hub_cli.py`: not a conflict — intentional shims. No action needed.
- `migrations/0007*` prefix collision: ✅ FIXED (9dc3e0b) — renamed
  `0007_v3_isrc_partial_unique.py` → `0015_v3_isrc_partial_unique.py`.
  Runner updated with LEGACY_FILENAME_ALIAS for idempotency on existing DBs.

### 7.4 Open items — structural audit follow-ups (targeted PRs)

- E1 (`tagslut/storage/migrations/0007*`): verify/lock policy to prevent future numeric-prefix collisions; runner currently applies in lexicographic filename order.
- E2 (`tagslut/metadata/models.py` vs `tagslut/metadata/models/`): decide whether to remove/rename the file-module or formalize it as an explicit shim; imports in codebase target `tagslut.metadata.models.*` submodules.
- E3 (`tagslut/cli/scan.py`, `tagslut/cli/track_hub_cli.py` vs `tagslut/cli/commands/*`): decide whether to keep these compatibility re-export modules and document their intended lifespan.

### 7.4 Script and docs cleanup: COMPLETE — see docs/CLEANUP_MANIFEST.md (2026-04-12)

---

## 8 — Copilot+ scope (editor only)

Inline completions, quick chat about open files in VS Code. Not for agentic tasks.

---

## 9 — Reserved for Claude Code (rate-limit budget)

Prompts for PR 12–15 and Phase 2 seam: done.
Use budget for: token bridge design (§20), download strategy revision (§21),
ReccoBeats provider spec (§22), Beatport token refresh research (§18 phase 3).

---

## 10 — Clean slate: new DB, new config: ✅ COMPLETE (2026-03-22)

DB paths:
  LEGACY: `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db`
  FRESH:  `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`

---

## 11 — Why the legacy DB cannot be trusted

Root cause: identity model built on MusicBrainz Picard-written tags.

Rules:
- Do not migrate identity rows from legacy DB to fresh DB
- Picard must never touch files tagslut manages going forward
- Legacy DB is read-only archaeology only — use `--db LEGACY_PATH` explicitly

---

## 12 — DB and backup audit: COMPLETE (2026-03-21)

Epoch renamed EPOCH_2026-03-04 → LEGACY_2026-03-04_PICARD.
Backup policy: one backup per significant session, named `music_v3.bak.YYYYMMDD.db`. Keep last two.

---

## 13 — Script, docs, log cleanup: COMPLETE (2026-03-22)

See `docs/CLEANUP_MANIFEST.md`.

---

## 14 — Ingestion provenance migration: ✅ COMPLETE (commit bef5931)

Four columns on `track_identity`: `ingested_at`, `ingestion_method`,
`ingestion_source`, `ingestion_confidence` — all NOT NULL, no DEFAULT.

---

## 15 — TIDAL OAuth refactor: COMPLETE (2026-03-21)

Commit: `3a3595c`. Global mutable state removed, monotonic clock, private naming.

---

## 16 — Migration 0013: five-tier confidence CHECK: COMPLETE (2026-03-24)

`ingestion_confidence` CHECK allows: `verified` | `corroborated` | `high` | `uncertain` | `legacy`

Verification: `poetry run pytest tests/storage/v3/test_migration_0013.py tests/storage/v3/test_migration_runner_v3.py -q` → 10 passed

---

## 17 — Postman API collection: COMPLETE (2026-03-21)

Final commit: `14c9e29`. All collection cleanup, v2 TIDAL migration, auth guards done.

Remaining operator task: run Validation Run in Collection Runner with live TIDAL token.
Pass: `5b` + `5c` both log `CORROBORATED`.

---

## 18 — Credential management consolidation ✅ COMPLETE

### Phase 1 ✅ COMPLETE
- `docs/CREDENTIAL_MANAGEMENT.md` written with `tokens.json` as operator source of truth
- Beatport provider prefers `TokenManager` / `tokens.json` before `BEATPORT_ACCESS_TOKEN`
- `tagslut token-get <provider>` added as shell-facing token lookup command

### Phase 2 ✅ COMPLETE (commit 1326d8e)
- Both harvest scripts migrated to `tagslut token-get beatport`
- `beatport_import_my_tracks.py` archived under `tools/archive/` (was not active)

### Phase 3 ✅ COMPLETE
- `TokenManager.refresh_beatport_token()` implemented in `auth.py`
- Tries refresh_token flow first; falls back to client_credentials if configured
- Falls through to manual DevTools paste instruction if neither works

---

## 19 — TIDAL v2 provider migration: ✅ COMPLETE (2026-03-26)

All TIDAL-related fixes landed on `dev` through commit `50062ea`:

| Fix | File | Commit | Status |
| --- | --- | --- | --- |
| `search_by_isrc` v2 next-link pagination | `tidal.py` | `db326ca` | ✅ |
| Lambda mock `limit=5` stubs (4 tests) | `test_tidal_beatport_enrichment.py` | `50062ea` | ✅ |
| `_make_request` mypy override — match parent signature | `tidal.py` | `50062ea` | ✅ |
| `_parse_duration_ms` docstring — v1 numeric / v2 ISO 8601 | `tidal.py` | `50062ea` | ✅ |
| Wire v2 attributes: `key_scale`, `tone_tags`, `popularity` | `tidal.py` + `types.py` | `50062ea` | ✅ |
| `TidalSeedExportStats` field alignment | `tidal.py` | `50062ea` | ✅ |

`poetry run mypy tagslut/metadata/providers/tidal.py --ignore-missing-imports` — clean ✅
`poetry run pytest tests/test_tidal_beatport_enrichment.py -v` — 12 passed ✅

Notes:
- TIDAL v2 `/tracks/{id}` attributes confirmed: `bpm`, `key`, `keyScale`, `toneTags`, `popularity`,
  `explicit`, `mediaTags`, `duration` (ISO 8601), `isrc`, `copyright`, `title`, `version`
- Audio feature fields (`energy`, `danceability`, `valence`, etc.) are **not** in TIDAL v2 —
  these require a third-party source (ReccoBeats or similar); see §22
- Beatport remains the authority for BPM/key when TIDAL returns null (sparse coverage)
- `genres` relationship available via `?include=genres` but not yet wired; add when needed

---

## 20 — tiddl → tokens.json bridge → **Codex** ⬅ COMPLETE (2026-04-01)

Implemented in commit `5f04481` and earlier.

### Problem

`TagTokenManager` reads only from `~/.config/tagslut/tokens.json`.
`tiddl` stores its session (including `refresh_token`) in `~/.tiddl/config.toml`.
These are completely separate auth states — tagslut fires "tidal token expired" warnings
even when tiddl has a live authenticated session.

### Fix

Add a fallback read in `tagslut/metadata/auth.py` → `load_tokens()`:
if `tokens.json` has no `tidal` section or an empty `refresh_token`, attempt to
read `~/.tiddl/config.toml` (or `TIDDL_CONFIG` env override) and import the
`refresh_token` from the `[token]` section. Write it into `tokens.json` so future
reads are self-healing.

Config path reference: `docs/TIDDL_CONFIG.md`

**Verification:**
```bash
# Clear tidal from tokens.json, confirm tiddl has a live session, then:
poetry run tagslut index enrich --providers tidal --dry-run
# Must NOT print "tidal token expired"
```

**Done when:** `tagslut index enrich` runs without token warnings when `~/.tiddl/config.toml`
has a valid session.

**Commit:** `fix(auth): fallback tidal refresh_token from tiddl config.toml`

---

## 21 — Download strategy rewrite → **Claude Code** ⬅ COMPLETE (2026-04-01)

`docs/DOWNLOAD_STRATEGY.md` updated; Beatport downloads are explicit (not automatic fallback) and beatportdl is active.

### Problem

`docs/DOWNLOAD_STRATEGY.md` is outdated. It declares Beatport as metadata-only
and disables Beatport-as-audio-source fallback. This is wrong for two reasons:

1. Many tracks exist **only on Beatport** (white-label, promo, label exclusives)
2. TIDAL v2 now exposes BPM, key, keyScale, toneTags natively — partially replacing
   the old Beatport-as-sole-metadata-authority assumption

### New strategy (to document)

| Track situation | Audio source | Metadata source |
| --- | --- | --- |
| On TIDAL + Beatport | TIDAL (tiddl) | TIDAL for key/bpm/tone; Beatport for genre/label/catalog |
| On TIDAL only | TIDAL (tiddl) | TIDAL only |
| On Beatport only | Beatport download | Beatport native, no TIDAL enrichment needed |
| Neither | Manual | — |

`ingestion_method` already distinguishes these. Beatport downloads get
`provider_api` with `canonical_source=beatport`.

**Task:** Rewrite `docs/DOWNLOAD_STRATEGY.md` to reflect best-available-source.
Enable `FALLBACK_ENABLED=true` for Beatport-only tracks.
Update `INGESTION_PROVENANCE.md` cascade rules if affected.

---

## 22 — ReccoBeats provider stub → **Codex** (post-§20/21)

`EnrichmentResult` already has `canonical_energy`, `canonical_danceability`,
`canonical_valence`, etc. with comment `# never populated - Spotify audio features API was removed`.

ReccoBeats (used by algojuke/juke) is a third-party audio analysis API that provides
these Spotify-style audio features. Adding a `ReccoBeatsProvider` would populate
these fields without touching TIDAL or Beatport.

**Pre-requisites:**
- ReccoBeats API access confirmed (key obtained)
- `ProviderTrack` audio feature fields added (blocked on §19 — DONE)
- Cascade rules in enrichment updated to prefer ReccoBeats for these fields

**Task:** Write `tagslut/metadata/providers/reccobeats.py` as a minimal stub
with `fetch_by_isrc(isrc) -> Optional[ProviderTrack]` returning energy/danceability/valence.
Do not implement until API key is confirmed available.

---

## 23 — Provider architecture: capability registry + Qobuz + download adapters → **Codex** ⬅ COMPLETE (2026-04-01)

Operational Qobuz metadata is live as of 2026-04-01; ReccoBeats audio-features provider (energy/danceability/valence) live as of 2026-04-02.

Full design: `docs/codex/CODEX_PROVIDER_ARCHITECTURE_IMPLEMENTATION_PROMPTS.md`
Assessment: `tagslut_Provider_Architecture_Assessment_for_Qobuz__TIDAL__Beatport.md`

**Architecture decision**: Option C (capability-registry). Verdict: incremental, staged.
**Active providers at start**: Beatport + TIDAL only. This historical baseline
is superseded in current runtime defaults where Qobuz metadata is enabled by default
and remains non-authoritative for canonical identity promotion.
**Identity constraint**: Qobuz must not contribute to identity key derivation until corroboration
rules (ISRC match + authoritative provider agreement) are satisfied. This is enforced at both
application and schema levels.

**8-prompt execution chain** (sequential, no skipping):

| Prompt | Phase | Scope | Agent | Status |
| --- | --- | --- | --- | --- |
| Prompt 1 | 0 | Contract freeze + stale surface correction | Codex | COMPLETE (2026-04-01) |
| Prompt 2 | 1 | ProviderRegistry + `providers.toml` activation config | Codex | COMPLETE (2026-04-01) |
| Prompt 3 | 2a | Provider state model + `tagslut provider status` CLI | Codex | COMPLETE (2026-04-01) |
| Prompt 4 | 2b | Capability-aware metadata router | Codex | COMPLETE (2026-04-01) |
| Prompt 5 | 3 | Per-role activation model (metadata vs download) | Codex | COMPLETE (2026-04-01) |
| Prompt 6 | 4 | Qobuz scaffold, now metadata-on by default, identity-safe | Codex | COMPLETE (2026-04-01) |
| Prompt 7 | 5 | Qobuz + Beatport download provider adapters | Codex | COMPLETE (2026-04-01) |
| Prompt 8 | 6 | Stale surface archival + provider scope cleanup | Codex | COMPLETE (8677a4d) |

**Gate rules:**
- Stop after Prompt 4 and evaluate before proceeding to Prompt 5.
- Stop after Prompt 6 and validate Qobuz metadata operationally in staging before starting Prompt 7.
- Prompt 7 requires operator confirmation that Qobuz purchase-download workflow is accessible.
- Prompt 8 requires operator confirmation that no active workflows depend on `dj-download.sh`.

**Key config file**: `~/.config/tagslut/providers.toml` (new; created by Prompt 2)
Canonical key names (do not deviate):
- `providers.<name>.metadata_enabled`, `providers.<name>.download_enabled`
- `providers.<name>.trust` = `"dj_primary"` | `"secondary"` | `"do_not_use_for_canonical"`

**Dependency on §21**: The download strategy doc rewrite (§21) should be completed before or
concurrently with Prompt 5, since Prompt 5 formalises the per-role activation model that §21
describes at policy level.

---

## Prompt files index

| File | Task | Agent | Status |
| --- | --- | --- | --- |
| `resume-refresh-fix.prompt.md` | Fix `--resume` in `tools/get-intake` | Codex | COMPLETE |
| `intake-pipeline-hardening.prompt.md` | Intake pipeline 3-fix hardening | Codex | COMPLETE |
| `repo-cleanup.prompt.md` | Archive dead scripts and stale docs | Codex | COMPLETE |
| `dj-pipeline-hardening.prompt.md` | DJ pipeline discipline | Codex | COMPLETE (retired) |
| `dj-workflow-audit.prompt.md` | DJ workflow audit | Codex | COMPLETE |
| `dj-ffmpeg-validation.prompt.md` | FFmpeg output validation | Codex | COMPLETE |
| `lexicon-reconcile.prompt.md` | Lexicon snapshot import and reconcile strategy | Codex | First slice implemented |
| `open-streams-post-0010.prompt.md` | Write DJ pipeline post | Codex | Ready |
| `postman-api-optimize.prompt.md` | Beatport/TIDAL API collection | Postman | COMPLETE |
| `CODEX_PROVIDER_ARCHITECTURE_IMPLEMENTATION_PROMPTS.md` | Provider architecture (8 prompts) | Codex | Ready (§23) |

Prompts needed (author in Claude.ai before delegating):
- `reccobeats-provider-stub.prompt.md` — for §22

Prompts authored and ready:
- `tiddl-token-bridge.prompt.md` — for §20 ← **give to Codex now**
- `docs/DOWNLOAD_STRATEGY.md` — rewritten for §21 (no Codex prompt needed; doc only)
