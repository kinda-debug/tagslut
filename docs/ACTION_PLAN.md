### 1. DB state summary

- **FRESH DB (canonical)**: `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`
- **Symlink trap**: `/Users/georgeskhawam/Projects/tagslut_db/music_v3.db` does not exist (confirmed missing; must remain absent).
- **Schema migrations (v3)**: `MAX(schema_migrations.version)=16` (latest note: `0016_tidal_audio_fields.sql`). Migrations `0017_*` and `0018_*` exist in repo but are not recorded on this DB as applied.
- **Row counts (current)**:
  - `track_identity`: 24,494 (by `ingestion_method`×`ingestion_confidence` group totals)
  - `asset_file`: 26,597
  - `mp3_asset`: 1,379
  - `dj_playlist`: 0
  - `reconcile_log`: 27,163
- **Ingestion distribution** (`track_identity`):
  - `migration|legacy`: 14,557
  - `multi_provider_reconcile|high`: 9,292
  - `multi_provider_reconcile|uncertain`: 5
  - `provider_api|high`: 638
  - `provider_api|uncertain`: 2

### 2. Prompt file audit

| prompt file | status | blocker / notes |
| --- | --- | --- |
| `.github/prompts/.DS_Store` | STALE | macOS artifact; not a prompt (should not be in repo). |
| `.github/prompts/absorb-mp3-to-sort.prompt.md` | READY | Operator-only filesystem work; requires `/Volumes/MUSIC` mounted and source dir present; uses `/Volumes/MUSIC/MP3_LIBRARY_CLEAN` conventions. |
| `.github/prompts/absorb-rbx-usb-bpdl-flacs.prompt.md` | READY | Operator-only filesystem work; requires `/Volumes/MUSIC` mounted and source USB/root paths present. |
| `.github/prompts/beets-sidecar-package.prompt.md` | COMPLETE | Deliverables exist (`docs/beets/*`, `beets-flask-config/beets/*`). |
| `.github/prompts/beets-sidecar-research.prompt.md` | STALE | Superseded by completed sidecar deliverables. |
| `.github/prompts/cleanup-djpool-home.prompt.md` | COMPLETE | Implemented on `dev` (`35bd008`). |
| `.github/prompts/codex_prompt_build_dj_seed_from_tree_rbx.md` | NEEDS_DESIGN | A standalone tool exists (`tools/build_dj_seed_from_tree_rbx`), but this prompt targets a full CLI+tests feature; decide whether to keep it as tools-only or integrate into `tagslut dj`. |
| `.github/prompts/consolidate-playlists.prompt.md` | READY | Operator-only filesystem work under `/Volumes/MUSIC/playlists/`; ensure dry-run path reviewed before apply. |
| `.github/prompts/dj-missing-tests-week1.prompt.md` | COMPLETE | All referenced test files exist; collection succeeds. |
| `.github/prompts/dj-pool-wizard-transcode.prompt.md` | READY | Verification prompt; depends on mounted volumes and a controlled dry-run plan (no writes). |
| `.github/prompts/docs-housekeeping-2026-04.prompt.md` | NEEDS_DESIGN | Some deliverables exist (`docs/COMMAND_GUIDE.md`, whitepapers moved to `docs/reference/`), but `docs/ARCHITECTURE.md` still contains “Explicit 4-stage pipeline (canonical)” drift; update scope to current docs surface. |
| `.github/prompts/docs-housekeeping-2026-04b.prompt.md` | NEEDS_DESIGN | Archival list conflicts with current repo state (e.g., `docs/CLEANUP_MANIFEST.md` intentionally active); re-scope to targeted doc fixes only. |
| `.github/prompts/feat-beets-sidecar.prompt.md` | STALE | Sidecar config/docs + deps are already present on `dev`; prompt’s “branch-only” guidance is outdated. |
| `.github/prompts/feat-intake-spotiflac.prompt.md` | STALE | SpotiFLAC support exists (`tagslut/intake/spotify.py`, tests, v3 migration `0017_*`); remaining action is applying pending migrations on the FRESH DB. |
| `.github/prompts/feat-spotify-intake-path.prompt.md` | STALE | song.link resolver exists (`tagslut/intake/spotify.py`); remaining action is applying pending migrations on the FRESH DB (if required). |
| `.github/prompts/feat-tidal-native-fields.prompt.md` | COMPLETE | Migration `0016_tidal_audio_fields.sql` is applied on the FRESH DB (schema_migrations version 16) and columns exist in `track_identity`. |
| `.github/prompts/lexicon-reconcile.prompt.md` | NEEDS_DESIGN | High-impact multi-task session touching DB+external volumes; prompt contains historical counts/assumptions and requires updated prerequisites + operator approval gates. |
| `.github/prompts/mp3-consolidate.prompt.md` | COMPLETE | Implemented on `dev` (`b9f8b73`). |
| `.github/prompts/phase1-pr10-identity-service.prompt.md` | STALE | Phase 1 PR chain is marked COMPLETE in `docs/ROADMAP.md` (commit `767df22` referenced). |
| `.github/prompts/phase1-pr12-identity-merge.prompt.md` | STALE | Phase 1 PR chain COMPLETE (`195efc7` referenced in `docs/ROADMAP.md`). |
| `.github/prompts/phase1-pr14-agent-docs-update.prompt.md` | STALE | Phase 1 PR chain COMPLETE (`8a0b00d` referenced in `docs/ROADMAP.md`). |
| `.github/prompts/phase1-pr15-phase2-seam.prompt.md` | STALE | Phase 2 seam COMPLETE (`d992d20` referenced; `classify_ingestion_track()` exists + tests present). |
| `.github/prompts/phase1-pr9-migration-0006-merge.prompt.md` | STALE | Phase 1 PR chain COMPLETE (`5995983` referenced in `docs/ROADMAP.md`). |
| `.github/prompts/repo-audit-and-plan.prompt.md` | COMPLETE | This audit output is `docs/ACTION_PLAN.md`. |
| `.github/prompts/repo-cleanup-supplement.prompt.md` | BLOCKED | Repo currently has a dirty working tree (deleted scripts + new `scripts/archive/*` + modified tools); reconcile/commit or revert before running further cleanup prompts. |
| `.github/prompts/repo-cleanup.prompt.md` | BLOCKED | Same blocker as above (requires operator decision: commit vs revert the in-progress cleanup changes). |

### 3. Open work — ranked by execution order

## 1. Add hard guard against LEGACY DB usage
**Status**: UNBLOCKED
**Agent**: Codex
**Prompt**: needs authoring
**Depends on**: nothing
**Done when**: any `--db` / `$TAGSLUT_DB` path containing `LEGACY_2026-03-04_PICARD` (or `/LEGACY/`) fails fast with a hard error before any writes.
**Notes**: `tagslut/utils/db.py:resolve_cli_env_db_path()` currently accepts legacy paths; `tagslut/cli/commands/get.py` and `START_HERE.sh` do not enforce “FRESH only”.

## 2. Apply pending v3 migrations on the FRESH DB (0017, 0018)
**Status**: OPERATOR-ONLY
**Agent**: Operator
**Prompt**: needs authoring
**Depends on**: 1
**Done when**: `schema_migrations` on `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db` records versions `17` and `18` (notes `0017_spotify_intake_ingestion_method.py`, `0018_blocked_cohort_state.sql`) and the new tables they introduce are visible in `sqlite_master`.
**Notes**: At time of this audit, the DB reports max version `16`; `tagslut/storage/v3/migration_runner.py:run_pending_v3()` will apply `.py` and `.sql` migrations from `tagslut/storage/v3/migrations/` once invoked against the DB.

## 3. Fail loudly on expired Qobuz user session during enrichment
**Status**: UNBLOCKED
**Agent**: Codex
**Prompt**: needs authoring
**Depends on**: nothing
**Done when**: an expired Qobuz session causes `ts-enrich` / enrichment batch to stop with a clear operator-actionable error (not silent “0 results”).
**Notes**: Current behavior logs 401/403 as WARNING in `tagslut/metadata/providers/qobuz.py` and continues.

## 4. Make `/Volumes/MUSIC` mount a hard preflight gate for volume-dependent operations
**Status**: UNBLOCKED
**Agent**: Codex
**Prompt**: needs authoring
**Depends on**: nothing
**Done when**: `START_HERE.sh` and the primary wrappers (`tools/get`, `tools/get-intake`, and any `ts-*` wrappers) stop before doing any filesystem writes if `/Volumes/MUSIC` is not mounted (or required subpaths missing).
**Notes**: Current `START_HERE.sh` warns but proceeds; `tools/get` can create unintended local directories when the volume is absent.

## 5. Resolve `$MP3_LIBRARY` ambiguity (MP3_LIBRARY vs MP3_LIBRARY_CLEAN vs Apple Music)
**Status**: NEEDS-DESIGN
**Agent**: Operator
**Prompt**: needs authoring
**Depends on**: nothing
**Done when**: there is exactly one documented, enforced “DJ MP3 root” for April 2026 workflow, and all defaults (`.env`, `START_HERE.sh`, `tools/get`, CLI help text) match it.
**Notes**: Multiple defaults still point at `/Volumes/MUSIC/MP3_LIBRARY`; docs also reference `/Volumes/MUSIC/MP3_LIBRARY_CLEAN`; operator model mentions Apple Music folder as the actual Rekordbox source.

## 6. Fix beatportdl Ctrl+C hang in `ts-get <beatport_url>` operator loop
**Status**: NEEDS-DESIGN
**Agent**: Operator
**Prompt**: needs authoring
**Depends on**: nothing
**Done when**: Beatport URL intake does not require manual Ctrl+C after every run, or the wrapper prints a single explicit instruction and exits cleanly without hanging.
**Notes**: Identified as audit finding F-04 (2026-04-09).

## 7. Decide and implement an MP3 writeback / COMM-noise cleanup path for Apple Music MP3s
**Status**: NEEDS-DESIGN
**Agent**: Operator
**Prompt**: needs authoring
**Depends on**: 5
**Done when**: there is an operator-facing command to (a) write back DB-enriched tags to MP3s where policy allows, and/or (b) clear the noisy COMM frame consistently for Apple Music-managed MP3s.
**Notes**: Audit finding F-07; current writeback is FLAC-centric.

## 8. Add an operator-friendly reviewer for `centralize_lossy_pool` conflict manifests
**Status**: UNBLOCKED
**Agent**: Codex
**Prompt**: needs authoring
**Depends on**: 5
**Done when**: there is a CLI/report that surfaces `conflict_isrc_duration` groups (from the JSONL manifest) into a human-reviewable report and optionally produces an execution plan.
**Notes**: Audit finding F-08; current workflow implies manual JSONL reading.

## 9. Unify or clearly deprecate `tools/get` vs `tagslut get` (cohort state / fix semantics)
**Status**: NEEDS-DESIGN
**Agent**: Claude Code
**Prompt**: needs authoring
**Depends on**: 2, 5
**Done when**: operator workflow uses one entrypoint that reliably records cohorts and enables `tagslut fix`, or docs explicitly declare the difference and steer usage accordingly.
**Notes**: `tagslut get` uses cohort tracking (`tagslut/cli/commands/get.py` + `_cohort_state.py`); `tools/get` does not.

## 10. Add a review gate for quarantine GC (no silent deletes)
**Status**: NEEDS-DESIGN
**Agent**: Operator
**Prompt**: needs authoring
**Depends on**: nothing
**Done when**: quarantine cleanup requires an explicit review/confirm step (or a staged “plan then execute” model) before deletions.
**Notes**: Audit finding F-12 (`tools/review/quarantine_gc.py` deletes based on age).

## 11. Fix doc drift in `docs/ARCHITECTURE.md` DJ pipeline language
**Status**: UNBLOCKED
**Agent**: Codex
**Prompt**: `.github/prompts/docs-housekeeping-2026-04.prompt.md` (re-scope first)
**Depends on**: 5, 9
**Done when**: `docs/ARCHITECTURE.md` no longer labels the retired 4-stage DJ pipeline as “canonical” anywhere, and the active M3U-based workflow is the primary description.
**Notes**: Audit finding F-09; `docs/COMMAND_GUIDE.md` already contains a “Legacy reference (RETIRED)” block, but `docs/ARCHITECTURE.md` still has “Explicit 4-stage pipeline (canonical)”.

## 12. Lexicon reconcile (v3 DJ + Lexicon DB integration)
**Status**: BLOCKED
**Agent**: Operator
**Prompt**: `.github/prompts/lexicon-reconcile.prompt.md`
**Depends on**: 1, 2, 5, 8
**Done when**: Lexicon metadata is reconciled into the v3 DB with a resumable log/checkpoint trail, and DJ pipeline outputs (MP3 state + playlists/export) are consistent with the current operator workflow.
**Notes**: High-risk multi-session work touching external DB (`/Volumes/MUSIC/lexicondj.db`) and large MP3 roots; prompt requires re-validation against current FRESH DB state.

## 13. DJ admission backfill is an ongoing operational task
**Status**: OPERATOR-ONLY
**Agent**: Operator
**Prompt**: needs authoring
**Depends on**: nothing
**Done when**: after each significant intake batch, `dj backfill --dry-run` is reviewed and then executed (as needed) with expected deltas only.
**Notes**: Roadmap §3.5 explicitly defines this as re-runnable, not a one-time milestone.

## 14. Structural audit follow-ups (E1–E3)
**Status**: NEEDS-DESIGN
**Agent**: Claude Code
**Prompt**: needs authoring
**Depends on**: nothing
**Done when**: a policy is locked for migration filename/versioning collisions (E1), and compatibility shims for `tagslut/metadata/models.py` and `tagslut/cli/*.py` are either formalized or retired with documented lifespan (E2, E3).
**Notes**: See `docs/ROADMAP.md` §7.4 and `docs/CLEANUP_MANIFEST.md` Phase E.

## 15. Resolve dirty working tree from in-progress cleanup
**Status**: OPERATOR-ONLY
**Agent**: Operator
**Prompt**: `.github/prompts/repo-cleanup.prompt.md` (or revert)
**Depends on**: nothing
**Done when**: `git status --short` is clean (either commit the script archival/moves or revert them), and stashes are intentionally kept or dropped.
**Notes**: Current status shows deleted scripts + new `scripts/archive/*` and modified `tools/absorb_*` scripts.

## 16. Restore or author the missing “open streams post” prompt referenced by the roadmap
**Status**: BLOCKED
**Agent**: Claude Code
**Prompt**: needs authoring (expected path: `.github/prompts/open-streams-post-0010.prompt.md`)
**Depends on**: nothing
**Done when**: the referenced prompt exists and matches current repo state, or the roadmap is updated to point to the correct prompt file.
**Notes**: `docs/ROADMAP.md` references a prompt that is not present in `.github/prompts/`.

### 4. Items confirmed complete — do not reopen

- Phase 1 PR chain (migration 0006, identity service, identity merge, backfill, docs update, phase2 seam): commits referenced in `docs/ROADMAP.md` (`5995983`, `767df22`, `195efc7`, `1e965b0`, `8a0b00d`, `d992d20`).
- DJ workflow audit: `16ee5ca`.
- FFmpeg output validation + wizard failure surfacing: `de59b4f`.
- XML validation gate + migration 0015 audit additions: `b9576ab`.
- Qobuz routing via streamrip in `tools/get`: `4065946`.
- Beatport circuit-breaker on first auth failure: `1205f7a`.
- `mp3_consolidate` executor added: `b9f8b73`.
- Legacy DJPool staging dir from home deleted: `35bd008`.

### 5. Operator-only checklist

- Verify `/Volumes/MUSIC` is mounted before any `ts-get`, `tools/get`, `tools/get-intake`, or filesystem-moving scripts.
- Perform Qobuz user re-login when required (`tagslut auth login qobuz`); never assume a session token is live.
- Refresh Beatport credentials via beatportdl interactive flow when required; keep `tokens.json` in sync.
- Apply v3 migrations to the FRESH DB only after confirming the DB path is `.../FRESH_2026/...`.
- Resolve any dirty working tree (commit vs revert) before running cleanup/archival prompts.
- Run `git filter-repo` / force-push operations only with full operator intent and downtime tolerance.

### 6. DB path safety rules (permanent)

- Canonical DB path for all work is: `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`.
- The legacy DB at `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db` must never be used for writes.
- The old symlink trap at `/Users/georgeskhawam/Projects/tagslut_db/music_v3.db` is confirmed **gone** and must never be recreated.
- Any agent/operator who sees a `--db` argument (or `$TAGSLUT_DB`) that does not include `FRESH_2026` must stop and verify before proceeding.

### 7. Known Codex failure patterns observed in this repo

- **DB path confusion**: uses `$TAGSLUT_DB` from a stale shell, accidentally writing to LEGACY; correct behavior is to hard-error on legacy path patterns and to print the resolved DB provenance before any write.
- **Silent provider failure**: treats provider 401/403 as a non-fatal warning and continues, producing “0 data” runs; correct behavior is to fail fast (or hard-mark provider as unavailable) when the operator must intervene.
- **Volume-not-mounted writes**: creates local directories under `/Volumes/MUSIC/...` when the volume is absent; correct behavior is preflight gating and explicit errors before writes.
- **Doc drift over-trust**: follows older docs/prompts that conflict with current operator model; correct behavior is to treat code/tests + `docs/ROADMAP.md` as source of truth and re-scope stale prompts.
- **Migration/version drift**: assumes `V3_SCHEMA_VERSION` is authoritative while `run_pending_v3()` applies migrations from disk; correct behavior is to verify the live DB’s `schema_migrations` and ensure migrations are both present and applied.
- **Entry-point equivalence assumption**: treats `tools/get` and `tagslut get` as interchangeable; correct behavior is to preserve cohort-state semantics (or document the difference loudly) before advising operators.
