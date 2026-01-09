# Repository Inventory (Evidence-First)

This inventory documents every file currently in the repo and how it supports the same goal: forensic, evidence-preserving FLAC recovery, auditing, and deduplication. Files are grouped by role. If a file is a generated artifact, it is explicitly labeled as such.

## How to Use This Inventory

- **Core code** lives in `dedupe/` and `tools/`.
- **Operational scripts** live in `scripts/` (shell, python, JXA).
- **One-off analysis tools** live at repo root (used during investigations).
- **Generated artifacts** are stored at repo root as CSV/TXT/JSON outputs; they are evidence, not code.

If a file is listed as *generated artifact*, it is not required for normal execution. Keep or archive for audit purposes.

---

## Core Package (`dedupe/`)

- `dedupe/__init__.py` — package entry.
- `dedupe/cli.py` — CLI entrypoints and argument parsing.
- `dedupe/deduper.py` — high-level deduplication orchestration.
- `dedupe/fingerprints.py` — audio fingerprint utilities.
- `dedupe/global_recovery.py` — global recovery workflow logic.
- `dedupe/health_score.py` — health scoring logic.
- `dedupe/healthcheck.py` — health checks for repo + data.
- `dedupe/healthscore.py` — legacy health score helper (kept for compatibility).
- `dedupe/hrm_relocation.py` — relocation logic for HRM review bucket.
- `dedupe/integrity_scanner.py` — integrity scan orchestration.
- `dedupe/manifest.py` — manifest model + helpers.
- `dedupe/matcher.py` — dedupe match engine.
- `dedupe/metadata.py` — metadata extraction helpers.
- `dedupe/picard_path.py` — Picard path parsing utilities.
- `dedupe/rstudio_parser.py` — R-Studio recovery name parsing.
- `dedupe/scanner.py` — file scanner (DB + integrity).
- `dedupe/step0.py` — initial scan / baseline pipeline.

### Core Submodules (`dedupe/core/`)

- `dedupe/core/__init__.py` — core module entry.
- `dedupe/core/decisions.py` — decision rules (keep/replace/quarantine).
- `dedupe/core/hashing.py` — hashing tiers and helpers.
- `dedupe/core/integrity.py` — integrity checks (FLAC validity).
- `dedupe/core/matching.py` — match ranking and scoring.
- `dedupe/core/metadata.py` — metadata quality scoring.

### DB Layer (`dedupe/db/`, `dedupe/storage/`)

- `dedupe/db/__init__.py` — DB package.
- `dedupe/db/schema.py` — schema helpers.
- `dedupe/storage/__init__.py` — storage package.
- `dedupe/storage/models.py` — DB models.
- `dedupe/storage/queries.py` — SQL queries.
- `dedupe/storage/schema.py` — schema definitions + migrations.

### Utilities (`dedupe/utils/`)

- `dedupe/utils/__init__.py` — utils entry.
- `dedupe/utils/cli_helper.py` — CLI helpers.
- `dedupe/utils/config.py` — config loading/validation.
- `dedupe/utils/db.py` — DB helpers.
- `dedupe/utils/library.py` — library layout helpers.
- `dedupe/utils/logging.py` — logging utilities.
- `dedupe/utils/parallel.py` — concurrency helpers.
- `dedupe/utils/paths.py` — path parsing helpers.

### External Integration (`dedupe/external/`)

- `dedupe/external/__init__.py` — external package entry.
- `dedupe/external/picard.py` — Picard integration helpers.

---

## Tools (`tools/`)

These are primary operator CLIs. Most are read-only unless explicitly described.

- `tools/__init__.py` — tools package entry.
- `tools/README.md` — tools overview.
- `tools/analyze_malformed_volumes.py` — detect malformed path volumes.
- `tools/compare_dbs.py` — compare two DBs (schema + record stats).
- `tools/db_upgrade.py` — schema upgrade tool.
- `tools/dupeguru_bridge.py` — bridge to dupeguru outputs.
- `tools/export_dupe_groups.py` — export dedupe groups for review.
- `tools/finalize_picard_map.py` — build Picard mapping output.
- `tools/group_missing_by_volume.py` — group missing files by volume.
- `tools/manual_ingest.py` — manual ingestion helper (operator-run).
- `tools/move_to_hrm.py` — relocate HRM review files.
- `tools/recommend_keepers.py` — recommend canonical keepers.
- `tools/scan_flac_integrity.py` — FLAC integrity scan wrapper.
- `tools/verify_final_library_daily.sh` — daily verification cron script.
- `tools/find_corrupt_flacs.sh` — shell helper for corrupt FLAC detection.
- `tools/listen_dupes.sh` — play duplicate pairs for review.
- `tools/open_dupe_pair.sh` — open duplicate pair in player.
- `tools/review_needed.sh` — list items requiring review.
- `tools/scan_final_library.sh` — shell wrapper for final library scan.

### Tools: DB Utilities (`tools/db/`)

- `tools/db/doctor.py` — DB health checks.
- `tools/db/resolve_db_path.py` — DB resolution helper (read vs write).

### Tools: Decisions (`tools/decide/`)

- `tools/decide/__init__.py` — decision module entry.
- `tools/decide/apply.py` — apply decision plan (writes allowed only when enabled).
- `tools/decide/recommend.py` — generate decision plan (read-only).

### Tools: Integrity (`tools/integrity/`)

- `tools/integrity/__init__.py` — integrity module entry.
- `tools/integrity/scan.py` — primary multi-root scanner.

### Tools: Review (`tools/review/`)

- `tools/review/__init__.py` — review helpers package.

---

## Scripts (`scripts/`)

Operator scripts and pipelines. See `docs/scripts_reference.md` for usage notes.

### Root (`scripts/`)

- `scripts/README.md` — script index and usage principles.
- `scripts/backup_dbs.sh` — DB backup helper.
- `scripts/fast_scan_library.sh` — fast scan wrapper.
- `scripts/quarantine_small_dupes.py` — quarantine small/short duplicates.
- `scripts/recover_workflow.py` — recovery automation.
- `scripts/safe_to_delete_presence.py` — safe deletion presence check.
- `scripts/scan_not_scanned.py` — resume scanning NOT_SCANNED rows.
- `scripts/validate_config.py` — config validation.

### Python (`scripts/python/`)

- `scripts/python/fix_empty_metadata.py` — fill missing metadata.
- `scripts/python/group_bad_flacs.py` — group bad FLACs.
- `scripts/python/offline_qobuz_playlist_dedupe.py` — offline playlist dedupe.
- `scripts/python/qobuz_playlist_dedupe.py` — online playlist dedupe.
- `scripts/python/rank_duplicates.py` — rank duplicate candidates.
- `scripts/python/rebuild_metadata.py` — rebuild metadata for healthy FLACs.
- `scripts/python/reorg_canonical_library.py` — reorganize canonical layout.
- `scripts/python/rescan_and_merge.py` — rescan and merge into DB.
- `scripts/python/scan_final_library.py` — final library scan.
- `scripts/python/update_extra_json.py` — update extra JSON fields.

### Shell (`scripts/shell/`)

- `scripts/shell/_resolve_db_path.sh` — resolve DB paths safely.
- `scripts/shell/apply_dedupe_plan.sh` — apply dedupe plan.
- `scripts/shell/build_final_library.sh` — build final library DB.
- `scripts/shell/check_folder_status.sh` — folder status report.
- `scripts/shell/clean_empty_dirs_commune.sh` — remove empty dirs on COMMUNE.
- `scripts/shell/dedupe_commune_move_dupes.sh` — move non-canonical dupes.
- `scripts/shell/export_canonical_library.sh` — export canonical library.
- `scripts/shell/finalize_library.sh` — finalize library state.
- `scripts/shell/fix_missing_metadata.sh` — patch missing metadata.
- `scripts/shell/full_workspace_cleanup.sh` — clean workspace outputs.
- `scripts/shell/recovery_only_pipeline.sh` — recovery-only pipeline.
- `scripts/shell/report_canonical_summary.sh` — report canonical summary.
- `scripts/shell/scan_all_sources_and_build_final.sh` — scan + build final.
- `scripts/shell/scan_final_library.sh` — shell scan wrapper.
- `scripts/shell/setup.sh` — setup bootstrap.
- `scripts/shell/verify_commune_dedup_state.sh` — verify COMMUNE state.

### JXA (`scripts/jxa/`)

- `scripts/jxa/yate_menu_dump.js` — Yate menu extraction (macOS).

---

## Docs (`docs/`)

- `docs/acoustid_validation_guide.md` — AcoustID validation procedure.
- `docs/architecture.md` — architectural overview.
- `docs/CODEX_BACKGROUND.md` — Codex background context.
- `docs/CODEX_PROMPT.md` — Codex working prompt reference.
- `docs/configuration.md` — configuration reference.
- `docs/DB_BACKUP.md` — DB backup procedure.
- `docs/FAST_WORKFLOW.md` — fast scan/dedupe workflow.
- `docs/PATHS_FROM_FILE_USAGE.md` — ingest from path file usage.
- `docs/process_flow.md` — end-to-end flow.
- `docs/RECOVERY_WORKFLOW.md` — recovery-first pipeline.
- `docs/SYSTEM_SPEC.md` — system spec index.
- `docs/scripts_reference.md` — scripts quick reference.
- `docs/staging_review_playbook.md` — review playbook for staging.
- `docs/plans/RECOVERY_EXECUTION_PLAN.md` — execution plan.
- `docs/plans/RECOVERY_EXECUTION_PLAN.pdf` — execution plan (PDF).
- `docs/plans/RECOVERY_PLAN.md` — recovery plan.
- `docs/plans/cleanup_plan.md` — cleanup plan.
- `docs/examples/reacquire_manifest.csv` — example manifest.
- `docs/examples/step0_plan.json` — example plan.

---

## Tests (`tests/`)

- `tests/__init__.py` — tests package entry.
- `tests/conftest.py` — test fixtures.
- `tests/test_cli.py` — CLI behavior.
- `tests/test_config.py` — config parsing.
- `tests/test_db_upgrade.py` — DB migration tests.
- `tests/test_global_recovery.py` — recovery pipeline tests.
- `tests/test_hashing_tiers.py` — hashing tier tests.
- `tests/test_health_score.py` — health score tests.
- `tests/test_healthcheck.py` — healthcheck tests.
- `tests/test_hrm_relocation.py` — HRM relocation tests.
- `tests/test_ingest_with_health.py` — ingest + health tests.
- `tests/test_manifest.py` — manifest tests.
- `tests/test_matcher.py` — matcher tests.
- `tests/test_metadata.py` — metadata tests.
- `tests/test_picard_reconcile.py` — Picard reconcile tests.
- `tests/test_repo_structure.py` — repo structure tests.
- `tests/test_rstudio_parser.py` — R-Studio parser tests.
- `tests/test_scanner.py` — scanner tests.
- `tests/test_step0_pipeline.py` — step0 pipeline tests.
- `tests/test_utils.py` — utilities tests.
- `tests/storage/__init__.py` — storage tests package.
- `tests/storage/test_upsert_normalization.py` — storage upsert tests.
- `tests/tools/__init__.py` — tools tests package.
- `tests/utils/__init__.py` — utils tests package.
- `tests/core/__init__.py` — core tests package.

---

## Artifacts (`artifacts/`)

- `artifacts/README.md` — artifact usage notes.
- `artifacts/db/.gitkeep` — placeholder for DB outputs.
- `artifacts/logs/.gitkeep` — placeholder for logs.
- `artifacts/manifests/.gitkeep` — placeholder for manifests.
- `artifacts/reports/.gitkeep` — placeholder for reports.
- `artifacts/tmp/.gitkeep` — placeholder for tmp files.

---

## Patches (`patches/`)

- `patches/patch.patch` — patch artifact.
- `patches/patch_paths_full.txt` — patch input (full paths).
- `patches/patch_missing_files.txt` — patch input (missing files).

---

## Root-Level Tooling (One-Off, Evidence-Only)

These scripts support forensic analysis and evidence collection. They are read-only unless explicitly noted.

- `aggregate_missing_path_twins.py` — aggregate checksum twins.
- `aggregate_missing_path_twins_ro_bad.py` — aggregate with bad volume (RO).
- `aggregate_missing_path_twins_ro_bad_commune.py` — aggregate with bad + COMMUNE (RO).
- `aggregate_missing_path_twins_ro_bad_commune_vault.py` — aggregate with bad + COMMUNE + Vault (RO).
- `bucket_missing_paths_by_twin_location.py` — bucket missing paths by twin location.
- `bucket_missing_paths_by_twin_location_ro_bad_commune.py` — bucket with bad + COMMUNE (RO).
- `bucket_missing_paths_by_twin_location_ro_bad_commune_vault.py` — bucket with bad + COMMUNE + Vault (RO).
- `build_commune_M_manifests.py` — build staging manifest + candidate list.
- `build_master_orphan_reconciliation.py` — build master reconciliation CSV.
- `build_orphan_unmatched_investigation_list.py` — build unmatched investigation list.
- `compare_fs_existence_bad.py` — compare bad volume existence sets.
- `convert_paths_to_excel.py` — split paths to Excel columns (openpyxl).
- `convert_to_excel.py` — alternate path-to-Excel converter.
- `generate_duplicates.py` — generate duplicate groups (analysis helper).
- `match_orphans_in_commune_by_checksum.py` — match orphans against COMMUNE hashes.
- `match_orphans_in_quarantine.py` — basename matching against quarantine inventory.
- `match_orphans_in_quarantine_by_checksum.py` — checksum matching against quarantine hashes.
- `missing_paths_RECOVERY_TARGET_report.py` — missing path report (DB-driven).
- `reconcile_orphan_sidecar_from_fs.py` — sidecar reconciliation to on-disk files.
- `reconcile_orphans_commune_quarantine.py` — consolidate COMMUNE + quarantine matches.
- `rollup_orphan_reconciliation.py` — per-orphan rollup.
- `scan_commune_flac_sha256.py` — hash all COMMUNE FLACs (SHA-256).
- `update_fs_existence_commune_ro.py` — update COMMUNE existence CSVs (RO).
- `update_fs_existence_vault_ro.py` — update Vault existence CSVs (RO).

---

## Root-Level Config and Project Files

- `.DS_Store` — macOS Finder metadata (local).
- `.editorconfig` — editor formatting rules.
- `.flake8` — Python lint config.
- `.gitignore` — git ignore rules.
- `CHANGELOG.md` — change history.
- `CODEOWNERS` — code ownership.
- `CONTRIBUTING.md` — contribution guide.
- `LICENSE` — license.
- `MANIFEST.in` — packaging manifest.
- `Makefile` — build/test helpers.
- `README.md` — main overview.
- `USAGE.md` — usage notes.
- `config.example.toml` — sample config.
- `config.toml` — local config (operator-specific).
- `poetry.lock` — lockfile.
- `pyproject.toml` — package metadata.
- `requirements.txt` — pip dependencies.
- `Codex Audit & Arbitration Prompt.md` — audit prompt reference.
- `copilot_chat.md` — chat transcript (local).
- `plan.json` — decision plan artifact.
- `plan_after_vault_cleanup.json` — plan artifact (vault cleanup).
- `output.zip` — archive artifact.
- `your_database.sqlite` — local DB sample.

---

## Root-Level Generated Artifacts (Evidence)

These are outputs produced by analysis scripts. They are not part of the core runtime and should be archived, not edited.

### Existence and Prefix Summaries

- `fs_existence_Volumes__COMMUNE__R2.csv`
- `fs_existence_Volumes__COMMUNE__Root.csv`
- `fs_existence_Volumes__COMMUNE___PROMOTION_STAGING.csv`
- `fs_existence_Volumes__RECOVERY_TARGET__Root.csv`
- `fs_existence_Volumes__Vault__RC2.csv`
- `fs_existence_Volumes__Vault__RECOVERED_TRASH.csv`
- `fs_existence_Volumes__Vault__Root.csv`
- `fs_existence_Volumes__Vault__Vault.csv`
- `fs_existence_Volumes__bad__.dedupe_db.csv`
- `fs_existence_Volumes__bad__FINAL_LIBRARY.csv`
- `fs_existence_Volumes__bad___ALL_FLACS_FLAT.csv`
- `fs_existence_Volumes__bad___BAD_VS_DOTAD_DISCARDS.csv`
- `fs_existence_ro_Volumes__COMMUNE__R2.csv`
- `fs_existence_ro_Volumes__COMMUNE__Root.csv`
- `fs_existence_ro_Volumes__COMMUNE___PROMOTION_STAGING.csv`
- `fs_existence_ro_Volumes__Vault__RC2.csv`
- `fs_existence_ro_Volumes__Vault__RECOVERED_TRASH.csv`
- `fs_existence_ro_Volumes__Vault__Root.csv`
- `fs_existence_ro_Volumes__Vault__Vault.csv`
- `fs_existence_ro_Volumes__bad__.dedupe_db.csv`
- `fs_existence_ro_Volumes__bad__FINAL_LIBRARY.csv`
- `fs_existence_ro_Volumes__bad___ALL_FLACS_FLAT.csv`
- `fs_existence_ro_Volumes__bad___BAD_VS_DOTAD_DISCARDS.csv`
- `fs_existence_bad_comparison.csv`
- `fs_existence_commune_comparison.csv`
- `fs_existence_vault_comparison.csv`
- `fs_existence_paths_to_prepare.csv`
- `fs_existence_summary_by_prefix.csv`
- `fs_existence_summary_by_prefix_ro_bad.csv`
- `fs_existence_summary_by_prefix_ro_bad_commune.csv`
- `fs_existence_summary_by_prefix_ro_bad_commune_vault.csv`

### Prefix Roots and Path Decomposition

- `shortest_covering_prefixes.txt`
- `shortest_covering_prefixes_no_volumes.txt`
- `shortest_covering_prefixes_no_volumes_counts.csv`
- `shortest_covering_prefixes_no_volumes_union.txt`
- `shortest_covering_prefixes_no_volumes_union_counts.csv`
- `paths_exploded_components.csv`
- `paths_exploded_components.sql`
- `paths_volume_firstdir_counts.csv`
- `paths_incomplete_scan_db_b.csv`
- `paths_to_prepare_for_epoch.csv`
- `common_shortest_paths.csv`
- `FINAL_LIBRARY_path_columns.csv`

### Prefix Summaries (Per Root)

- `prefix_summary_Volumes__COMMUNE__R2.csv`
- `prefix_summary_Volumes__COMMUNE__Root.csv`
- `prefix_summary_Volumes__COMMUNE___PROMOTION_STAGING.csv`
- `prefix_summary_Volumes__RECOVERY_TARGET__Root.csv`
- `prefix_summary_Volumes__Vault__RC2.csv`
- `prefix_summary_Volumes__Vault__RECOVERED_TRASH.csv`
- `prefix_summary_Volumes__Vault__Root.csv`
- `prefix_summary_Volumes__Vault__Vault.csv`
- `prefix_summary_Volumes__bad__.dedupe_db.csv`
- `prefix_summary_Volumes__bad__FINAL_LIBRARY.csv`
- `prefix_summary_Volumes__bad___ALL_FLACS_FLAT.csv`
- `prefix_summary_Volumes__bad___BAD_VS_DOTAD_DISCARDS.csv`

### Missing Paths and Twin Analysis

- `missing_paths_RECOVERY_TARGET_checksum_matches.csv`
- `missing_paths_RECOVERY_TARGET_checksum_matches_ro_bad.csv`
- `missing_paths_RECOVERY_TARGET_checksum_matches_ro_bad_commune.csv`
- `missing_paths_RECOVERY_TARGET_checksum_matches_ro_bad_commune_vault.csv`
- `missing_paths_RECOVERY_TARGET_checksum_twin_summary.csv`
- `missing_paths_checksum_twins_by_prefix.csv`
- `missing_paths_checksum_twins_by_prefix_ro_bad.csv`
- `missing_paths_checksum_twins_by_prefix_ro_bad_commune.csv`
- `missing_paths_checksum_twins_by_prefix_ro_bad_commune_vault.csv`
- `missing_paths_checksum_twin_collapse.csv`
- `missing_paths_checksum_twin_collapse_ro_bad.csv`
- `missing_paths_checksum_twin_collapse_ro_bad_commune.csv`
- `missing_paths_checksum_twin_collapse_ro_bad_commune_vault.csv`
- `missing_paths_without_any_checksum_twin.csv`
- `missing_paths_without_any_checksum_twin_ro_bad.csv`
- `missing_paths_without_any_checksum_twin_ro_bad_commune.csv`
- `missing_paths_without_any_checksum_twin_ro_bad_commune_vault.csv`
- `missing_paths_bucket_orphans.csv`
- `missing_paths_bucket_orphans_ro_bad_commune.csv`
- `missing_paths_bucket_orphans_ro_bad_commune_vault.csv`
- `missing_paths_bucket_other_twins.csv`
- `missing_paths_bucket_other_twins_ro_bad_commune.csv`
- `missing_paths_bucket_other_twins_ro_bad_commune_vault.csv`
- `missing_paths_bucket_present_bad_commune.csv`
- `missing_paths_bucket_present_bad_commune_vault.csv`
- `missing_paths_bucket_bad_present.csv`
- `relative_path_collisions.csv`
- `relative_path_collisions_by_pair.csv`
- `prefix_overlap_matrix.csv`

### Orphan Reconciliation and Quarantine

- `orphans_sidecar_reconciliation.csv`
- `orphans_sidecar_reconciliation_summary.csv`
- `orphans_reconciliation_master.csv`
- `orphans_reconciliation_quarantine_commune.csv`
- `orphans_reconciliation_rollup.csv`
- `orphans_reconciliation_rollup_summary.csv`
- `orphans_unmatched_investigation_list.csv`
- `orphans_without_quarantine_or_commune_match.csv`
- `orphans_in_quarantine_by_basename.csv`
- `orphans_in_quarantine_by_checksum.csv`
- `orphans_checksum_no_quarantine_match.csv`
- `orphans_in_commune_by_checksum.csv`
- `orphans_checksum_no_commune_match.csv`
- `orphans_commune_checksum_summary.csv`
- `orphans_commune_checksum_collisions.csv`
- `orphans_quarantine_checksum_summary.csv`
- `quarantine_inventory.csv`
- `quarantine_checksums.csv`

### COMMUNE Hashing

- `commune_flac_sha256.csv`
- `commune_flac_scan_errors.csv`

### Duplicate/Conflict Reports

- `checksum_conflicts.csv`
- `internal_duplicates.json`
- `internal_duplicates_array.json`
- `generate_duplicates.py` (script; see above)

### Misc Analysis Artifacts

- `db_a_unique_paths.csv`
- `files_to_delete.csv`
- `failed.txt`
- `missing_13.txt`
- `tracks_tree_RECOVERY_RARGET.txt`
- `recovery_accepted_all.txt`
- `uh.txt`
- `uh_paths.xlsx`
- `test_bc_camplight.txt`

---

## Alignment Notes

- Files under `dedupe/`, `tools/`, and `scripts/` implement the core, evidence-first workflow.
- Root-level analysis scripts and CSV outputs are **forensic artifacts** produced during investigation. They are read-only, reproducible, and should be archived when a phase is complete.
- Local operator files (`config.toml`, `.DS_Store`, `copilot_chat.md`) are not part of the core pipeline.
