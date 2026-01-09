# Scripts Reference (Operator-Focused)

This file documents scripts under `scripts/`. These are operator helpers and pipelines. Most are read-only unless explicitly stated.

For core CLIs and long-lived workflows, use the tools in `tools/` and the package code in `dedupe/`.

## Safety Conventions

- **RO** = read-only (no file moves or DB writes).
- **RW** = writes to disk and/or DB; run only when you intend changes.
- When unsure, review the script header before running.

---

## Root Scripts (`scripts/`)

- `scripts/backup_dbs.sh` — Backup SQLite DBs. **RW** (writes backup files).
- `scripts/fast_scan_library.sh` — Quick scan wrapper. **RW** (DB writes).
- `scripts/quarantine_small_dupes.py` — Move tiny/short dupes to quarantine. **RW**.
- `scripts/recover_workflow.py` — Recovery workflow automation. **RW** (moves/copies).
- `scripts/safe_to_delete_presence.py` — Verify delete candidates exist. **RO**.
- `scripts/scan_not_scanned.py` — Resume scanning NOT_SCANNED rows. **RW** (DB writes).
- `scripts/validate_config.py` — Validate config file. **RO**.
- `scripts/README.md` — Script overview and usage principles.

---

## Python Utilities (`scripts/python/`)

### Metadata Management

- `scripts/python/rebuild_metadata.py` — Rebuild metadata for healthy FLACs. **RW** (writes metadata outputs).
- `scripts/python/fix_empty_metadata.py` — Fix empty metadata fields. **RW**.
- `scripts/python/update_extra_json.py` — Update DB JSON fields. **RW**.

### Duplicate Ranking

- `scripts/python/rank_duplicates.py` — Rank duplicates by quality/preference. **RO** (report output).

### Library Operations

- `scripts/python/reorg_canonical_library.py` — Reorganize canonical layout. **RW** (moves/copies).
- `scripts/python/rescan_and_merge.py` — Rescan + merge into canonical DB. **RW** (DB writes).
- `scripts/python/scan_final_library.py` — Scan final library. **RW** (DB writes).

### Qobuz Playlist Tools

- `scripts/python/qobuz_playlist_dedupe.py` — Online playlist dedupe (API). **RO** (network).
- `scripts/python/offline_qobuz_playlist_dedupe.py` — Offline playlist dedupe. **RO**.

### Volume/FLAC Analysis

- `scripts/python/group_bad_flacs.py` — Group bad FLACs for analysis. **RO**.

---

## Shell Pipelines (`scripts/shell/`)

### Library Build and Scan

- `scripts/shell/build_final_library.sh` — Build final library DB. **RW** (DB writes).
- `scripts/shell/scan_all_sources_and_build_final.sh` — Scan all sources + merge. **RW**.
- `scripts/shell/scan_final_library.sh` — Scan final library. **RW**.
- `scripts/shell/finalize_library.sh` — Finalize library. **RW**.

### Deduplication and Cleanup

- `scripts/shell/dedupe_commune_move_dupes.sh` — Move non-canonical dupes. **RW**.
- `scripts/shell/apply_dedupe_plan.sh` — Apply dedupe plan. **RW**.
- `scripts/shell/clean_empty_dirs_commune.sh` — Remove empty dirs. **RW**.

### Recovery and Reporting

- `scripts/shell/recovery_only_pipeline.sh` — Recovery-first pipeline. **RW**.
- `scripts/shell/report_canonical_summary.sh` — Canonical summary report. **RO**.
- `scripts/shell/verify_commune_dedup_state.sh` — Verify dedupe state. **RO**.

### Utilities

- `scripts/shell/_resolve_db_path.sh` — Resolve DB path safely. **RO**.
- `scripts/shell/check_folder_status.sh` — Folder status report. **RO**.
- `scripts/shell/export_canonical_library.sh` — Export canonical library. **RW** (writes exports).
- `scripts/shell/fix_missing_metadata.sh` — Patch missing metadata. **RW**.
- `scripts/shell/full_workspace_cleanup.sh` — Workspace cleanup. **RW**.
- `scripts/shell/setup.sh` — Setup bootstrap. **RW** (writes config scaffolding).

---

## JXA (`scripts/jxa/`)

- `scripts/jxa/yate_menu_dump.js` — Extract Yate menus (macOS). **RO**.

---

## Notes

- If a script is not listed here, it should be treated as experimental or deprecated.
- For structured, repeatable operations, prefer the `tools/` CLIs and workflows in `docs/`.
