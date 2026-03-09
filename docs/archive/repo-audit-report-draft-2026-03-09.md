<!-- Status: Archived document. One-off audit draft retained for history; not authoritative. -->

Now I have all the documents needed. Let me produce the audit.

***

# tagslut — Repository Audit Report
### Pass 1: A (Surface Consistency) + B (Schema/Model Integrity) + E (Doc/Code Drift)
**Date:** 2026-03-09 | **Depth:** MODERATE | **Strictness:** STRICT | **Perspective:** MAINTAINER

***

## Repository Identity

- **Name:** tagslut
- **Language/stack:** Python 3.11, Poetry, SQLite, Click CLI, Flask (optional/web)
- **Scale:** 13+ declared deps, 20k+ track library, ~150+ files inferred from PRs and commit history
- **Maturity:** v3.0.0, post-Phase-5 decommission, Phase 1 v3 identity migration in-flight
- **Primary operator:** Single developer, CLI-driven

***

## Status Update (2026-03-09)

- This audit draft is partially superseded by later repo work and verification.
- `tagslut/storage/v3/identity_service.py` exists in this checkout, and the focused identity-service suite currently passes (`11 passed`).
- `scripts/validate_v3_dual_write_parity.py` and `scripts/lint_policy_profiles.py` are present in this checkout.
- The legacy `library_tracks` DDL was verified in `tagslut/storage/schema.py`; `library_track_key TEXT UNIQUE` matches `_mirror_to_library_tracks()` and validates its `ON CONFLICT(library_track_key)` assumption.
- `fix/migration-0006` contains `0007_v3_isrc_partial_unique.py` at commit `d853b0a`, verified in a detached worktree. The current `dev` checkout does not yet contain that file.

***

## A. Surface Consistency

**Method:** Cross-referenced `AGENT.md`, `docs/SURFACE_POLICY.md`, `docs/SCRIPT_SURFACE.md`, `pyproject.toml` `[project.scripts]`, open PRs, and the most recent 30 commits for command/script existence vs. documentation claims.

### Findings

| # | Severity | Location | Finding | Evidence | Recommendation | Confidence |
|---|----------|----------|---------|----------|----------------|-----------|
| A1 | HIGH | `AGENT.md` "CLI Command Surface" vs `docs/SURFACE_POLICY.md` §Canonical | `AGENT.md` lists `tagslut canonize`, `tagslut enrich-file`, `tagslut explain-keeper` under "Specialized commands" as active. `SURFACE_POLICY.md` explicitly classifies these as **hidden top-level commands by policy** — not canonical, not operator-facing. | `AGENT.md`: "Specialized commands: …canonize…enrich-file…explain-keeper"; `SURFACE_POLICY.md`: "Hidden top-level commands by policy: tagslut canonize …" | Remove those three from `AGENT.md` "Specialized commands" and add a "Policy-hidden commands" subsection matching `SURFACE_POLICY.md` wording. | HIGH |
| A2 | HIGH | `AGENT.md` "CLI Command Surface" vs `docs/SURFACE_POLICY.md` | `AGENT.md` does not list `tagslut init`, `tagslut gig`, or `tagslut export` — all three are canonical per `SURFACE_POLICY.md` §Canonical Surface items 9–11 and `SCRIPT_SURFACE.md` items 9–11. | `SURFACE_POLICY.md`: "9. `poetry run tagslut gig`… 10. `poetry run tagslut export`… 11. `poetry run tagslut init`"; `AGENT.md` CLI surface stops at `tagslut explain-keeper` | Add `tagslut init`, `tagslut gig`, `tagslut export` to `AGENT.md` canonical command list. | HIGH |
| A3 | HIGH | `pyproject.toml` `[project.scripts]` | `pyproject.toml` declares **only** `tagslut = "tagslut.cli.main:cli"`. The `dedupe` alias is gone (correct). But this means if Phase 1 adds `tagslut ops backfill-v3` as a subcommand it must be a Click group under `cli`, not a separate entry point — **this is not documented anywhere as a constraint.** New contributors could accidentally add a second script entry point. | `pyproject.toml` line 33: `tagslut = "tagslut.cli.main:cli"` only | Add to `AGENT.md` "CLI Command Surface": "All subcommands must be Click groups registered under `tagslut.cli.main:cli`. No new entry points in `[project.scripts]`." | HIGH |
| A4 | MEDIUM | `docs/SURFACE_POLICY.md` §Change Control vs `AGENT.md` | `SURFACE_POLICY.md` §Change Control requires any surface change to update `docs/archive/legacy-root-docs-2026-03-06-md-cleanup/MOVE_EXECUTOR_COMPAT.md` and `docs/archive/REDESIGN_TRACKER.md`. `AGENT.md` has no mention of these change-control docs. Agents/contributors editing `AGENT.md` surface will not know to cascade. | `SURFACE_POLICY.md`: "Any change to canonical or transitional surface must update all of: …MOVE_EXECUTOR_COMPAT.md…REDESIGN_TRACKER.md" | Add a "Change Control" section to `AGENT.md` referencing the cascade list in `SURFACE_POLICY.md`. | HIGH |
| A5 | MEDIUM | `AGENT.md` "Common Commands" vs `docs/SCRIPT_SURFACE.md` | `AGENT.md` describes `tools/get-sync` as "Deprecated compatibility only." `SCRIPT_SURFACE.md` §Operational Wrappers item 4 describes it the same way. However, `AGENT.md` still shows it as an active example: `tools/get-sync <beatport-url>`. Operators who scan the Common Commands section will think it is supported. | `AGENT.md`: "tools/tiddl … tools/get-sync …" listed without deprecation warning inline | Add `# DEPRECATED` inline comment on the `tools/get-sync` example in `AGENT.md` and redirect to `tools/get`. | MEDIUM |
| A6 | MEDIUM | `docs/SCRIPT_SURFACE.md` §Operational Wrappers vs `AGENT.md` | `SCRIPT_SURFACE.md` documents `tools/tag-build`, `tools/tag-run`, and `tools/tag` (OneTagger wrappers) as canonical active entry points. `AGENT.md` has no mention of these three wrappers at all. Any contributor reading only `AGENT.md` (the agent guide) will not know these exist. | `SCRIPT_SURFACE.md` items 6–8; absent from `AGENT.md` | Add `tools/tag-build`, `tools/tag-run`, `tools/tag` to `AGENT.md` "Common Commands" under a "Metadata tagging" subsection. | HIGH |
| A7 | MEDIUM | `AGENT.md` "Work output zones" vs `SCRIPT_SURFACE.md` | `AGENT.md` correctly documents `FIX_ROOT`, `QUARANTINE_ROOT`, `DISCARD_ROOT`. `SCRIPT_SURFACE.md` item 1 (`tools/get`) also references them. However neither document specifies **which env var controls each root**, leaving the mapping implicit. `.env.example` is the only source of truth for var names, and it is not referenced in either doc. | `AGENT.md`: "FIX_ROOT — Salvageable…"; env var name not stated | In both docs, add: "Set via `FIX_ROOT`, `QUARANTINE_ROOT`, `DISCARD_ROOT` or the `$VOLUME_WORK/…` defaults. See `.env.example`." | MEDIUM |
| A8 | LOW | `docs/SURFACE_POLICY.md` §Validation Hooks item 16 | References `python scripts/validate_v3_dual_write_parity.py`. No such script appears in any commit log, and no PR introduces it. It may not exist. | Not found in commit history of last 30 commits; `scripts/` dir not fully listed but this specific file absent | Mark as `[UNVERIFIED — check if script exists]` in `SURFACE_POLICY.md` or remove. | MEDIUM |
| A9 | LOW | `docs/SURFACE_POLICY.md` §Validation Hooks item 17 | References `python scripts/lint_policy_profiles.py`. Same issue as A8 — not seen in commit history. | Same evidence as A8 | Same: verify existence or remove from doc. | MEDIUM |

**Assumptions made:** `pyproject.toml` `[project.scripts]` is the sole source of installed entry points. The `tagslut/` package directory is structured as a Click group hierarchy with `tagslut.cli.main:cli` as root. Scripts in `tools/` are not installed, just direct-executable wrappers.

***

## B. Schema/Model Integrity

**Method:** Cross-referenced `docs/DB_V3_SCHEMA.md`, `docs/CORE_MODEL.md`, the Phase 1 PLAN.md (attached), open PR #179 (ISRC migration), and the `pyproject.toml` for any ORM/migration framework signals. [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/43550134/454e009d-cff8-4ea1-8639-fa4ff212c37d/PLAN.md)

### Findings

| # | Severity | Location | Finding | Evidence | Recommendation | Confidence |
|---|----------|----------|---------|----------|----------------|-----------|
| B1 | CRITICAL | `docs/DB_V3_SCHEMA.md` `track_identity` vs PLAN.md Phase 1 | The schema doc lists `track_identity` columns as: `isrc`, `beatport_id`, `artist_norm`, `title_norm`, `duration_ref_ms`, `ref_source`. PLAN.md Phase 1 requires adding `tidal_id`, `qobuz_id`, `deezer_id`, `traxsource_id`, `musicbrainz_id`, `itunes_id`, `merged_into_id`, plus 12 canonical metadata columns. **The schema doc is not updated.** Any contributor reading `DB_V3_SCHEMA.md` today gets the pre-Phase-1 schema and will write code against wrong columns. | `DB_V3_SCHEMA.md` "track_identity Key columns"; PLAN.md "Extend track_identity to hold canonical recording fields" | Update `DB_V3_SCHEMA.md` to reflect all columns that migration `0006_track_identity_canonical.py` will add **before** that migration lands. Tag the section with `# Phase 1 in-flight`. | HIGH |
| B2 | CRITICAL | `docs/CORE_MODEL.md` Rule 3 vs `docs/DB_V3_SCHEMA.md` `asset_link` | `CORE_MODEL.md` Rule 3: "Every asset must map to exactly one active identity link." `DB_V3_SCHEMA.md` `asset_link` says "Operational contract: each asset has exactly one active link." But PLAN.md says `active=1` is the **runtime** link — one asset may have **multiple** `asset_link` rows (one per historical identity attempt) with only one `active=1`. The "exactly one" language in both docs is ambiguous: does it mean exactly one row, or exactly one `active=1` row? This ambiguity will cause incorrect `INSERT` vs `UPSERT` decisions in implementation. | `CORE_MODEL.md` Rule 3; `DB_V3_SCHEMA.md`: "each asset has exactly one active link"; PLAN.md: "keep the table shape as-is, but treat `active=1` as the runtime link" | Clarify in both docs: "Each asset has exactly one `active=1` link at any time; multiple inactive historical links are permitted." | HIGH |
| B3 | HIGH | `docs/DB_V3_SCHEMA.md` `track_identity` | The schema doc does not document any indexes on `track_identity`. Given 20k+ tracks and a 5-step identity resolution chain (PLAN.md), **missing indexes are a functional correctness issue at scale**, not just a performance concern — resolution will time out or produce wrong results if queries do full scans. | `DB_V3_SCHEMA.md` has no "Indexes" section; PLAN.md lists 8 required indexes | Add an "Indexes" section to `DB_V3_SCHEMA.md` listing all required covering indexes for the resolution chain. Mark which are partial (`WHERE col IS NOT NULL`). | HIGH |
| B4 | HIGH | `docs/DB_V3_SCHEMA.md` vs PLAN.md `merged_into_id` | The `merged_into_id` column required by PLAN.md for collision handling is absent from `DB_V3_SCHEMA.md`. Code that reads `track_identity` without knowing about `merged_into_id` will surface stale/merged identity rows as canonical. | `DB_V3_SCHEMA.md` `track_identity` section; PLAN.md "normalize collisions…merged_into_id field" | Add `merged_into_id` to the schema doc with its FK constraint and the invariant: "Runtime reads must follow `merged_into_id` when non-null." | HIGH |
| B5 | HIGH | `docs/CORE_MODEL.md` "Forbidden" vs PLAN.md compatibility mirror | `CORE_MODEL.md` Forbidden item 2: "Do not mutate canonical identity fields in `asset_file`." But PLAN.md Phase 1 explicitly requires writing canonical fields **back** to `files` (legacy table) as a compatibility mirror — `files.canonical_*`, `files.library_track_key`. These are different tables (`asset_file` vs. legacy `files`), but the `files` table carries columns named `canonical_*` which could reasonably be read as violating the spirit of this rule. **The doc creates ambiguity about whether write-through to `files` is allowed.** | `CORE_MODEL.md` Forbidden 2; PLAN.md "files.canonical_* become mirrors derived from v3 identity/asset state" | Add a note to `CORE_MODEL.md`: "Write-through to the legacy `files` compatibility table is permitted via `IdentityService.write_through_to_legacy()` only. `asset_file.canonical_*` columns must not be added." | HIGH |
| B6 | MEDIUM | `docs/DB_V3_SCHEMA.md` `asset_file` `zone` column vs PR #180 | PR (https://github.com/tagslut/tagslut/pull/180) renames zone constants from `GOOD/BAD/QUARANTINE` to `library/djpool/archive`. The schema doc's `asset_file` lists `zone` as a column but does not document allowed values or the enum source. After #180 merges, valid zone values change but the schema doc has no place to reflect this. | `DB_V3_SCHEMA.md` `asset_file` "zone"; PR #180 body: "rename legacy zone mappings from `GOOD/BAD/QUARANTINE` to `library/djpool/archive`" | Add to `DB_V3_SCHEMA.md` `asset_file.zone`: "Enum values: `library`, `djpool`, `archive`, `quarantine` (active quarantine). Source: `tagslut/zones/core.py`." | MEDIUM |
| B7 | MEDIUM | `docs/DB_V3_SCHEMA.md` "Optional vs Core" vs `pyproject.toml` | The schema doc states "DJ-focused tables (e.g. `gig_sets`, `gig_set_tracks`) are optional." But `pyproject.toml` lists `pyrekordbox>=0.3,<1.0` as a **non-optional core dependency** — not in `[project.optional-dependencies]`. This means any installation of tagslut pulls in Rekordbox integration even in non-DJ deployments, contradicting the "optional overlay" model. | `pyproject.toml` line 29: `pyrekordbox` in `[project.dependencies]`; `DB_V3_SCHEMA.md`: "Core indexing…must work without DJ workflows" | Move `pyrekordbox` (and `roonapi` if applicable) to `[project.optional-dependencies]` under a `dj` extra. Update install docs accordingly. | MEDIUM |
| B8 | MEDIUM | `docs/DB_V3_SCHEMA.md` "Forbidden Patterns" item 3 vs `tools/review/` | Forbidden Pattern 3: "Direct DB path rewrites without corresponding successful `move_execution`." The scripts `tools/review/move_from_plan.py`, `tools/review/promote_by_tags.py`, and `tools/review/quarantine_from_plan.py` are described in `SCRIPT_SURFACE.md` as the canonical move execution path. But the schema doc's forbidden patterns apply to the DB layer — it is **UNVERIFIED** whether these scripts go through `move_execution` rows or write paths directly. | `DB_V3_SCHEMA.md` Forbidden 3; `SCRIPT_SURFACE.md` "tools/review/move_from_plan.py" as canonical | Add a doc assertion in `DB_V3_SCHEMA.md`: "All `tools/review/` scripts must create a `move_execution` row on success. Verify with `select count(*) from move_execution where status='success'` after each run." Mark current state as UNVERIFIED until code is reviewed. | MEDIUM |
| B9 | LOW | `docs/DB_V3_SCHEMA.md` `provenance_event` | The `provenance_event` table is described as "immutable audit event stream" but there is no documentation of what triggers event creation, what `event_type` values are valid, or who is responsible for writing events. Any new code path (e.g. the Phase 1 `IdentityService`) will not know whether to emit events or what type to use. | `DB_V3_SCHEMA.md` `provenance_event` section has no "trigger" or "event_type enum" documentation | Add to `DB_V3_SCHEMA.md` `provenance_event`: a "Valid event_type values" table and "Which operations must emit events" list. | MEDIUM |

**Assumptions made:** `tagslut/storage/schema.py` was inspected for legacy compatibility DDL. `library_tracks` is defined there with `library_track_key TEXT UNIQUE`, which matches `_mirror_to_library_tracks()` and confirms the `ON CONFLICT(library_track_key)` assumption is valid. The legacy `files` and `library_tracks` tables are in the same SQLite file but are not documented in `DB_V3_SCHEMA.md`.

***

## E. Doc/Code Drift

**Method:** Cross-referenced `AGENT.md`, `docs/WORKFLOWS.md` (existence confirmed), `docs/OPERATIONS.md` (existence confirmed), `docs/SURFACE_POLICY.md`, `docs/SCRIPT_SURFACE.md` against recent commits (last 30) for behavior changes that landed without corresponding doc updates.

### Findings

| # | Severity | Location | Finding | Evidence | Recommendation | Confidence |
|---|----------|----------|---------|----------|----------------|-----------|
| E1 | HIGH | `AGENT.md` "DJ MP3 Transcode and Sync" `Tag policy` | `AGENT.md` states: "Lyrics (USLT, SYLT) are always stripped." This is now **correct policy**, but it was introduced by commit [`0a34a97`](https://github.com/tagslut/tagslut/commit/0a34a97b3f0392c4b9f415e51c9eccfa535394ee) ("Limit DJ tag frames"). Before that commit, the import `SYLT, USLT` was still present in `transcoder.py:15`, implying they were used. The doc now says "always stripped" but the code still imports these symbols (F401 per baseline PR #181). **The code has not caught up to the documented policy.** | `AGENT.md` tag policy; commit `0a34a97`; PR #181 flake8 finding `transcoder.py:15 F401 SYLT USLT` | Fix is already identified (Stage 0.3 of the plan): remove the dead imports. This finding confirms the fix is both a lint issue **and** a doc/code drift issue — the import implies intended usage that contradicts the doc. | HIGH |
| E2 | HIGH | `AGENT.md` "Common Commands" vs commit [`a3416ee`](https://github.com/tagslut/tagslut/commit/a3416eed2e7dbe38982d76f366ef5f6743b71116) | The env var rename refactor commit changed variable names across config files and scripts. `AGENT.md` "Common Commands" shows env var names (`DJ_LIBRARY`, `MASTER_LIBRARY`, `DJ_ROOT`, `ROOT_TD`, `TIDDL_BIN`, `TIDDL_DOWNLOAD_ROOT`, `STAGING_ROOT`) but does **not** indicate which are the new canonical names vs. the old renamed ones. If any of these were renamed in `a3416ee`, every example in `AGENT.md` that uses the old name silently breaks. | Commit `a3416ee`: "Refactor environment variable names for clarity and consistency"; `AGENT.md` env var examples | Audit `a3416ee` diff to identify exactly which vars were renamed. Update every occurrence in `AGENT.md`. Mark the old names as deprecated with migration path. | HIGH |
| E3 | HIGH | `docs/SURFACE_POLICY.md` dated `2026-03-02` vs PR #177 (retire `dedupe` June 2026) | `SURFACE_POLICY.md` §Branding: "dedupe has been retired and is no longer shipped as a console script." PR (https://github.com/tagslut/tagslut/pull/177) is titled "feat: retire dedupe alias (scheduled June 2026)" — still **open**, not merged. The doc says it's already retired; the PR says it's scheduled. These are contradictory. | `SURFACE_POLICY.md` "dedupe has been removed"; PR #177 open and unmerged, description says "remove the retired dedupe console-script registration" | Until PR #177 is merged: `SURFACE_POLICY.md` wording should read "dedupe is deprecated and will be removed 2026-06-01." After merge: wording is correct. Do not merge docs before code. | HIGH |
| E4 | MEDIUM | `AGENT.md` "Tidal downloader" `TIDDL_BIN` documentation vs commit [`7d2b2f3`](https://github.com/tagslut/tagslut/commit/7d2b2f3b74914d5e018a87109d663e466046a422) | Commit `7d2b2f3` ("Enhance TIDDL wrapper with improved path handling and configuration synchronization") likely changed how `TIDDL_BIN`, `TIDDL_DOWNLOAD_ROOT`, and `~/.tiddl/config.toml` sync works. `AGENT.md` describes the TIDDL behavior but this may now be stale: "Syncs `~/.tiddl/config.toml` download_path to match resolved root." The sync logic was "enhanced" — the doc may describe the old behavior. | Commit `7d2b2f3`; `AGENT.md` "Tidal downloader" section | Review the diff of `7d2b2f3` and update `AGENT.md` TIDDL section to reflect current path resolution and config sync logic. Mark any changed env var priority order. | MEDIUM |
| E5 | MEDIUM | `docs/SCRIPT_SURFACE.md` §Recovery Command Status vs `SURFACE_POLICY.md` | `SCRIPT_SURFACE.md` says "tagslut recovery is a hidden minimal stub logger and does not implement the full move pipeline." `SURFACE_POLICY.md` lists `tagslut recovery ...` as a "Hidden top-level command by policy." But `AGENT.md` does not mention `tagslut recovery` at all — not even as hidden. An agent given only `AGENT.md` will not know this stub exists and may attempt to use `tagslut recovery` or implement against it. | `SCRIPT_SURFACE.md` "Recovery Command Status"; `SURFACE_POLICY.md` hidden commands list; absent from `AGENT.md` | Add to `AGENT.md` a "Hidden/Stub Commands" section: "`tagslut recovery` is a stub logger only. Do not route operator move workflows through it. Use `tools/review/` scripts instead." | MEDIUM |
| E6 | MEDIUM | `AGENT.md` "Work output zones" vs commit [`3b7bc7b`](https://github.com/tagslut/tagslut/commit/3b7bc7beb368eb7baba98c3302906aecd3cd957f) | Commit `3b7bc7b` introduced the `FIX_ROOT`/`QUARANTINE_ROOT`/`DISCARD_ROOT` split and added `quarantine_gc.py` and `plan_move_skipped.py`. `AGENT.md` correctly documents `quarantine_gc.py` usage. But `plan_move_skipped.py` is mentioned in `SCRIPT_SURFACE.md` (`tools/review/plan_move_skipped.py`) and absent from `AGENT.md`. | Commit `3b7bc7b` message; `SCRIPT_SURFACE.md` "tools/review/plan_move_skipped.py"; absent from `AGENT.md` | Add `tools/review/plan_move_skipped.py` to `AGENT.md` Common Commands under quarantine lifecycle, with its flags. | MEDIUM |
| E7 | LOW | `docs/PHASE1_STATUS.md` (1,065 bytes) | A `PHASE1_STATUS.md` file exists in `docs/`. Given Phase 1 is actively in-flight (5 open PRs), this document either reflects in-progress state or is already stale. Its contents are not surfaced in `AGENT.md`, `SURFACE_POLICY.md`, or the plan. If stale, it will mislead contributors about what Phase 1 has completed. | `docs/PHASE1_STATUS.md` exists (SHA: `ebbf603`); not referenced in `AGENT.md` or `SURFACE_POLICY.md` | Read `PHASE1_STATUS.md` and either: (a) update it to reflect current PR state, or (b) move it to `docs/archive/` if superseded by PLAN.md. Add a reference in `AGENT.md`. | MEDIUM |
| E8 | LOW | `docs/REDESIGN_TRACKER.md` (193 bytes) | At 193 bytes, `REDESIGN_TRACKER.md` in the `docs/` root is almost certainly a stub or empty tracker that has not been updated since it was created. `SURFACE_POLICY.md` §Change Control requires it to be updated on surface changes, but contributors have no way to know what format it expects. | File size 193 bytes; referenced in `SURFACE_POLICY.md` Change Control | Expand `REDESIGN_TRACKER.md` to a minimal table format: Phase | Status | Owner | Last Updated. Move the stub content to match that structure. | LOW |

***

## Updated Audit Prompt — Filled In

```markdown
## Repository Identity
- Name: tagslut
- Language/stack: Python 3.11, Poetry, SQLite (no ORM), Click CLI, Flask (optional web extra)
- Scale: ~150+ files, 20k+ track FLAC library, 13 core + 1 optional declared dep
- Maturity: v3.0.0, post-Phase-5 decommission, Phase 1 v3 identity migration in-flight
  (PRs #177–#181 open as of 2026-03-09)
- Primary operator: Single developer, CLI-driven, DJ/library management workflows

## Context Documents Verified Present in Repo
- AGENT.md (root)
- docs/ARCHITECTURE.md
- docs/CORE_MODEL.md
- docs/DB_V3_SCHEMA.md
- docs/OPERATIONS.md
- docs/PHASE1_STATUS.md  ← check for staleness (E7)
- docs/PHASE5_LEGACY_DECOMMISSION.md
- docs/PROGRESS_REPORT.md
- docs/PROJECT.md
- docs/SCRIPT_SURFACE.md
- docs/SURFACE_POLICY.md
- docs/TROUBLESHOOTING.md
- docs/WORKFLOWS.md
- docs/ZONES.md
- docs/DJ_POOL.md
- docs/DJ_REVIEW_APP.md
- docs/DJ_WORKFLOW.md
- docs/REDESIGN_TRACKER.md  ← 193 bytes, likely stub (E8)
- pyproject.toml
- REPORT.md
- CHANGELOG.md
- .env.example

## Still not present in this checkout / branch-specific:
- AGENTS.md (filename is AGENT.md — no 'S')
- `tagslut/storage/migrations/0007_v3_isrc_partial_unique.py` on `dev`
  ← present on `fix/migration-0006` at `d853b0a`, not merged here yet

## Recommended Next Audit Passes
- Pass 2: B (deep) + D — Attach schema.py, migration runner, and tools/review/ scripts
- Pass 3: C — Trace `tools/get <url> --dj` end-to-end
- Pass 4: J + I — Attach .env.example, all env_paths.py, zone YAML
```

***

## Priority Action List (Ordered)

1. **[B1+B4]** Update `DB_V3_SCHEMA.md` to reflect Phase 1 schema additions before migration lands — especially `merged_into_id` and all canonical columns.
2. **[B2]** Clarify `CORE_MODEL.md` Rule 3 ambiguity: "exactly one active link" vs. "exactly one row."
3. **[A1+A2]** Reconcile `AGENT.md` CLI surface list against `SURFACE_POLICY.md` — remove `canonize`/`enrich-file`/`explain-keeper` from "Specialized commands"; add `init`/`gig`/`export`.
4. **[E3]** Fix `SURFACE_POLICY.md` `dedupe` wording — it says retired when the retirement PR (#177) is still open.
5. **[E2]** Audit `a3416ee` diff and update all env var names in `AGENT.md` to post-rename canonical names.
6. **[A3]** Document the "one entry point only" constraint in `AGENT.md` to protect against accidental `[project.scripts]` additions.
7. **[B7]** Move `pyrekordbox` (and evaluate `roonapi`) to `[project.optional-dependencies][dj]` to honour the "DJ is optional overlay" model.
8. **[A8+A9]** Verify or remove `validate_v3_dual_write_parity.py` and `lint_policy_profiles.py` references from `SURFACE_POLICY.md`.
