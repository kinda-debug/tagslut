# Spring Clean Report — 2026-04-15

## Summary
I audited 170 surface files directly across CLI modules, named tool wrappers, loose root scripts, live docs, and prompts, plus targeted source/test scans for import and reference drift.

The largest mismatch is CLI/docs drift: `docs/SCRIPT_SURFACE.md` covers only a narrow canonical slice, while the live CLI tree still exposes `get`, `tag`, `fix`, `admin`, `ops`, `provider`, `postman`, `library`, `lexicon`, `master`, `v3`, and the `misc` helper commands.

One wrapper is broken today: `tools/beatport` execs `tools/get-sync`, but there is no root-level `tools/get-sync` file.

`docs/STAGING_OPS.md` matches the current staging root layout (`/Volumes/MUSIC/staging/` and the `SpotiFLACnext` / `SpotiFLAC` / `tidal` / `Apple` subroots).

Prompt hygiene is mixed: `.github/prompts/` has 99 files total, 70 under `archive/`, and many prompts still use agent-identity phrasing or lack an explicit “do not recreate existing deliverables” guard.

## CLI Surface

### Registered commands vs. documented commands

| Module | Registered surface | Help present? | In `docs/SCRIPT_SURFACE.md`? | Issues |
| --- | --- | --- | --- | --- |
| `tagslut/cli/commands/admin.py` | `admin` group with `intake/index/execute/verify/report/library/curate/dj` trees + `status` | Mixed | Partial | Big subtree not reflected in docs; several leaves have empty help |
| `tagslut/cli/commands/auth.py` | `auth` group + top-level `auth-tidal-logout` and `token-get` aliases | Mixed | Partial | Duplicate `token-get`; legacy top-level aliases still live |
| `tagslut/cli/commands/decide.py` | `decide profiles`, `decide plan` | Yes | No | Fine functionally, but not in canonical surface doc |
| `tagslut/cli/commands/dj.py` | `dj` group with `admit/backfill/classify/curate/export/gig-prep/prep-rekordbox/review-app/validate`, plus `lexicon`, `crates`, `role`, `xml` subgroups | Mixed | No | Help is uneven; lots of operational surface not documented |
| `tagslut/cli/commands/execute.py` | `execute move-plan/quarantine-plan/promote-tags` | Yes | Yes | Good surface, but docs still underdescribe inputs/side effects |
| `tagslut/cli/commands/export.py` | `export usb` | Yes | Yes | Fine |
| `tagslut/cli/commands/fix.py` | `fix` | No | No | Top-level help is blank |
| `tagslut/cli/commands/get.py` | `get` | No | No | Top-level help is blank; wrapper still exists alongside `intake` |
| `tagslut/cli/commands/gig.py` | `gig build/list/status/apply-rekordbox-overlay` | Yes | Yes | Fine |
| `tagslut/cli/commands/index.py` | `index register/check/register-mp3/duration-check/duration-audit/set-duration-ref/promote-classification/enrich/dj-flag/dj-autoflag/dj-status` | Mixed | Yes | Good core surface, but docs omit many leaves and the doc wording is older |
| `tagslut/cli/commands/intake.py` | `intake url/spotiflac/resolve/run/prefilter/process-root/stage` | Yes | Partial | Good core surface; docs should mention current stage names more explicitly |
| `tagslut/cli/commands/library.py` | `library import-rekordbox` | Yes | No | Missing from canonical surface doc |
| `tagslut/cli/commands/lexicon.py` | `lexicon import/import-playlists` | Yes | No | Missing from canonical surface doc |
| `tagslut/cli/commands/master.py` | `master scan` | Yes | No | Missing from canonical surface doc |
| `tagslut/cli/commands/misc.py` | `intake-mp3-to-sort-staging`, `tidal-seed`, `beatport-enrich`, `beatport-seed`, `tidal-enrich`, hidden `canonize/show-zone/explain-keeper/enrich-file`, `init` | Mixed | Partial | Hidden helper surface is only partially documented; several commands are operator-only shims |
| `tagslut/cli/commands/mp3.py` | `mp3 build/reconcile/scan/missing-masters/reconcile-library/reconcile-scan/verify-schema` | Yes | Yes | Good enough, but docs only mention a subset |
| `tagslut/cli/commands/ops.py` | `ops run-move-plan/plan-dj-library-normalize/relink-dj-pool/writeback-canonical` | Mixed | No | Missing from canonical surface doc |
| `tagslut/cli/commands/postman.py` | `postman ingest` | Yes | No | Missing from canonical surface doc |
| `tagslut/cli/commands/provider.py` | `provider status` | Mixed | No | Missing from canonical surface doc |
| `tagslut/cli/commands/report.py` | `report m3u/duration/plan-summary/dj-review` | Mixed | Yes | Help is blank on some leaves |
| `tagslut/cli/commands/tag.py` | `tag` + `curate fetch/batch-create/review/apply/export/sync-to-files` | No | No | Top-level help is blank |
| `tagslut/cli/commands/v3.py` | `v3 migrate`, `v3 provenance show` | Mixed | No | Missing from canonical surface doc |
| `tagslut/cli/commands/verify.py` | `verify duration/parity/receipts` | Yes | Yes | Good core surface |
| `tagslut/cli/commands/scan.py` | hidden `scan` group, `enqueue/run/status/issues/report` | No | No | Explicitly unregistered by main CLI; compatibility-only |
| `tagslut/cli/commands/track_hub_cli.py` | standalone `track-hub` style CLI entrypoint | Yes | No | Not part of main CLI tree; standalone shim only |

### Dead helpers

None. `_auth_helpers.py`, `_enrich_helpers.py`, `_index_helpers.py`, and `_cohort_state.py` are all imported by command modules.

### Command consistency issues

- `fix`, `get`, and `tag` have blank top-level help text.
- `auth token-get` exists both as a top-level alias and as `auth token-get`.
- `scan` is explicitly tested as unregistered, so the module exists only as a compatibility shim.
- `tools/beatport` is stale: it points at missing `tools/get-sync`.
- `docs/SCRIPT_SURFACE.md` omits live CLI surfaces for `ops`, `provider`, `postman`, `library`, `lexicon`, `master`, `v3`, and most `admin` / `misc` leaves.

## Tools Layer

### Active tools

- `tools/get`
- `tools/get-intake`
- `tools/get-report`
- `tools/get-help`
- `tools/enrich`
- `tools/auth`
- `tools/tag`
- `tools/tag-build`
- `tools/tag-run`
- `tools/tag-metadata`
- `tools/tag-audiofeatures`
- `tools/metadata`
- `tools/metadata-audit`
- `tools/tidal`
- `tools/tiddl`
- `tools/deemix`
- `tools/playlist-sync`
- `tools/mp3_reconcile_scan`
- `tools/build_dj_seed_from_tree_rbx`
- `tools/centralize_lossy_pool`
- active `tools/review/` operations: `process_root.py`, `move_from_plan.py`, `quarantine_from_plan.py`, `plan_move_skipped.py`, `quarantine_gc.py`, `promote_by_tags.py`, `plan_summary.py`, `pre_download_check.py`

### Orphaned tools

- `tools/beatport` is effectively orphaned in its current form because it targets a missing `tools/get-sync`.
- `tools/archive/` is mostly archival; most files there are not referenced by current docs/tests.

### Superseded tools

- `tools/beatport` is superseded by `tools/get` / `tagslut intake`.
- `tools/get-help` is superseded by `tools/get --help`.
- `tools/archive/build_export_v3.py` is superseded by `scripts/dj/build_pool_v3.py` and `tagslut dj pool-wizard`.
- `tools/archive/dj_review_app.py` is superseded by the CLI review path.

### Archive tools still with a live dependency

- `tools/archive/get-sync` is still indirectly referenced by `tools/beatport`, so it is the one archive wrapper that still matters operationally.

## Scripts Layer

### Active scripts

- `scripts/check_cli_docs_consistency.py`
- `scripts/audit_repo_layout.py`
- `scripts/lint_policy_profiles.py`
- `scripts/validate_v3_dual_write_parity.py`
- `scripts/dj/build_pool_v3.py`
- `scripts/dj/export_candidates_v3.py`
- `scripts/dj/export_ready_v3.py`
- `scripts/dj/profile_v3.py`
- `scripts/dj/report_missing_metadata_v3.py`
- `scripts/db/migrate_v2_to_v3.py`
- `scripts/db/verify_v3_migration.py`
- `scripts/db/check_promotion_preferred_invariant_v3.py`
- `scripts/db/report_identity_qa_v3.py`
- `scripts/db/backfill_v3_identity_links.py`
- `scripts/review/*` and `tools/review/*` operational plan/execution helpers referenced by tests and docs

### Root-level loose scripts (should be relocated)

- `scripts/filter_spotify_against_db.py` -> `scripts/spotify/filter_spotify_against_db.py` or `tools/`
- `scripts/rebuild_pool_library.py` -> `scripts/rekordbox/rebuild_pool_library.py` or `tools/`
- `scripts/rekordbox/rewrite_rekordbox_db_paths.py` -> keep under `scripts/rekordbox/`
- `scripts/rekordbox/rewrite_rekordbox_xml_paths.py` -> keep under `scripts/rekordbox/`

### Orphaned/superseded scripts

- `scripts/archive/build_export_v3.py` is archived and superseded by `scripts/dj/build_pool_v3.py`.
- `scripts/archive/capture_post_release_snapshot.py` is archived.
- `scripts/archive/filter_songshift_existing.py` is archived.
- `scripts/archive/reconcile_track_overrides.py` is archived.

## Codex Prompts

### Done (deliverable shipped)

- `add-ts-stage-command.md`
- `codex_prompt_build_dj_seed_from_tree_rbx.md`
- `dj-seed-from-tree-rbx.md`
- `clean-lossy-pool-builder.md`

### Active (in-flight or scheduled)

- `P1-inventory-all-locations.md`
- `P2-staging-intake-sweep.md`
- `P3-fix-column-names.md`
- `P3-fix2-year-fallback.md`
- `P3-resolve-unresolved.md`
- `P4-mp3-library-consolidation.md`
- `P5-final-audit-and-rekordbox-export.md`
- `P6-promote-staging.md`
- `P7-final-intake-pass.md`
- `qobuz-full-intake-pipeline.md`
- `staging_full_intake.md`
- `transcode-docs-and-staging-plan.md`
- `triage-work-dirs.md`

### Stale/orphan

- All files under `.github/prompts/archive/` are stale by location unless they are explicitly kept as historical records.
- `RUNBOOK.md` has no single concrete deliverable of its own; it is reference material, not an execution prompt.

### Policy violations (missing guard / agent identity)

- Many prompts lack an explicit “do not recreate existing deliverables” guard.
- Many archive prompts still start with “You are ...” and therefore violate prompt-authoring policy.
- Examples: `archive/dj-missing-tests-week1.prompt.md`, `archive/phase1-pr10-identity-service.prompt.md`, `archive/phase1-pr12-identity-merge.prompt.md`, `archive/repo-cleanup.prompt.md`, `archive/lexicon-reconcile.prompt.md`, `archive/intake-pipeline-hardening.prompt.md`.

## Docs

### Accurate and current

- `docs/PROJECT_DIRECTIVES.md`
- `docs/STAGING_OPS.md`
- `docs/OPERATOR_QUICK_START.md`
- `docs/DJ_POOL.md`
- `docs/WORKFLOWS.md`
- `docs/INGESTION_PROVENANCE.md`
- `docs/MULTI_PROVIDER_ID_POLICY.md`
- `docs/TIDDL_CONFIG.md`
- `docs/README.md`

### Stale or aspirational

- `docs/ROADMAP.md` is an active backlog/history doc, not a current-state reference.
- `docs/AUDIT_STATE_2026.md`, `docs/AUDIT_STATE_20260409.md`, and `docs/SESSION_REPORT_2026-04-01.md` are snapshots.
- `docs/ARCHITECTURE.md` is mostly current but still carries legacy DJ-pipeline language and should be read with its own caveat.
- `docs/SCRIPT_SURFACE.md` is partially stale because it omits live CLI surfaces and still presents an incomplete command map.

### Contradictions with `PROJECT_DIRECTIVES.md`

- None major on staging layout: `docs/STAGING_OPS.md` uses `/Volumes/MUSIC/staging/`, not the old `mdl/` path.
- The main contradiction is scope drift: `docs/SCRIPT_SURFACE.md` is not a complete inventory of the actual CLI surface that `PROJECT_DIRECTIVES.md` expects operators to use.

## Source Modules

### Dead modules (not imported by anything)

- `tagslut.cli.scan` is a compatibility re-export and is intentionally not registered in the main CLI.
- `tagslut.cli.track_hub_cli` is a standalone compatibility shim, not part of the main Click tree.

### Duplicated logic

- `tagslut/storage/migration_runner.py` and `tagslut/storage/v3/migration_runner.py` are parallel runners by design; the divergence is documented, but they still need continued hygiene.
- `tagslut/cli/scan.py` and `tagslut/cli/commands/scan.py` are compatibility wrapper + implementation.
- `tagslut/cli/track_hub_cli.py` and `tagslut/cli/commands/track_hub_cli.py` are compatibility wrapper + implementation.

### Stubs blocking functionality

- `tagslut/download/providers.py` still has `NotImplementedError` paths for major provider workflows.
- `tagslut/storage/v3/classification.py` explicitly raises `NotImplementedError("Phase 2 classification policy is not implemented")`.

## Tests

### Misplaced tests (proposed relocation)

- `tests/test_backfill_identity_v3.py` -> `tests/storage/v3/`
- `tests/test_check_promotion_preferred_invariant_v3.py` -> `tests/storage/v3/`
- `tests/test_db_v3_schema.py` -> `tests/storage/v3/`
- `tests/test_migrate_v2_to_v3.py` -> `tests/db/`
- `tests/test_report_identity_qa_v3.py` -> `tests/db/`
- `tests/test_report_missing_metadata_v3.py` -> `tests/dj/` or `tests/scripts/dj/`
- `tests/test_export_dj_candidates_v3.py` -> `tests/dj/` or `tests/scripts/dj/`
- `tests/test_export_ready_v3.py` -> `tests/dj/` or `tests/scripts/dj/`
- `tests/test_dj_export_builder_v3.py` -> `tests/scripts/archive/`
- `tests/test_build_pool_v3.py` -> `tests/dj/`

### Duplicate coverage

- Root-level v3 tests duplicate coverage already present under `tests/storage/` and `tests/exec/` for schema, migration, and DJ pipeline behavior.
- There is overlap between root-level script tests and the more focused `tests/exec/` contracts around intake and export flows.

### Brittle imports

- Many tests shell out to `scripts/*` and `tools/review/*` directly: `tests/test_repo_layout_audit_script.py`, `tests/test_cli_docs_consistency_script.py`, `tests/test_policy_lint_script.py`, `tests/test_v3_identity_scripts.py`, `tests/test_verify_v3_migration.py`, `tests/test_export_ready_v3.py`, `tests/test_report_missing_metadata_v3.py`, `tests/test_build_pool_v3.py`.
- `tests/cli/test_scan_cli.py` intentionally asserts the opposite of registration, which is fine but signals the compatibility-shim boundary.

## Prioritized action list

1. Fix or delete `tools/beatport`; its current `get-sync` dependency is broken.
2. Sync `docs/SCRIPT_SURFACE.md` to the live CLI tree, or remove the undocumented compatibility commands from the CLI.
3. Add real help text for `get`, `tag`, `fix`, and the blank-help leaf commands.
4. Relocate the loose root scripts into `scripts/rekordbox/` or `tools/`, then decide whether any are still worth keeping.
5. Archive or rewrite the stale prompts; add the missing “do not recreate existing deliverables” guard everywhere.
6. Move the root-level v3/script tests into the directory that matches the module they validate.
7. Decide whether `tagslut.cli.scan` and `tagslut.cli.track_hub_cli` stay as compatibility shims or are removed after the doc/CLI cleanup.
