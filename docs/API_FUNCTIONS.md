# API Functions Overview

This document inventories key functions and modules to guide restructuring.

## CLI and Entry Points
- dedupe/cli.py: `build_parser()`, `_command_scan()`, `_command_match()`, `_command_manifest()`, `_command_rescan_missing()`, `_command_health()`, `_command_health_batch()`, `run_healthscore()`, `_command_dedupe()`, `_command_hrm_move()`, `_command_relocate_hrm()`, `run_upgrade_db()`, `main()`

## Scanning & Metadata
- dedupe/scanner.py: `initialise_database()`, `prepare_record()`, `_existing_index()`, `_upsert_batch()`, `scan_library()`, `scan()`, `rescan_missing()`
- dedupe/metadata.py: `_run_ffprobe()`, `_parse_stream_info()`, `_extract_tags()`, `probe_audio()`

## Matching & Manifest
- dedupe/matcher.py: `load_library_entries()`, `load_recovery_entries()`, `_filename_similarity()`, `_size_difference()`, `_quality_classification()`, `_compute_score()`, `match_databases()`
- dedupe/manifest.py: `_priority_for()`, `_notes_for()`, `_rows_from_matches()`, `generate_manifest()`

## Integrity & Health
- dedupe/healthcheck.py: `_run_flac_test()`, `_normalise_tags()`, `_evaluate_tags()`, `evaluate_flac()`
- dedupe/healthscore.py: `score_file()`
- dedupe/core/integrity.py: `check_flac_integrity()`

## Decisions & HRM
- dedupe/deduper.py: `_canonical_sort_key()`, `deduplicate_database()`
- dedupe/core/decisions.py: `get_library_priority()`, `get_file_priority()`, `assess_duplicate_group()`
- dedupe/hrm_relocation.py: `relocate_hrm()` and helpers

## Storage & Utilities
- dedupe/storage/schema.py: `get_connection()`, `init_db()`, `initialise_library_schema()`
- dedupe/storage/queries.py: `upsert_library_rows()`, `fetch_records_by_state()`, `update_library_path()`, `record_picard_move()`, `upsert_file()`, `get_file()`, `get_files_by_checksum()`, `get_all_checksums()`
- dedupe/utils/__init__.py: `ensure_parent_directory()`, `iter_audio_files()`, `is_audio_file()`, `compute_md5()`, `read_json()`, `safe_int()`, `safe_float()`, `normalise_path()`, `chunks()`, `temporary_cwd()`, `as_dict()`
- dedupe/utils/parallel.py: `process_map()`
- dedupe/utils/paths.py: `list_files()`, `sanitize_path()`
- dedupe/utils/config.py: `get_config()`

## Tools (Selected)
- tools/scan_flac_integrity.py: `ensure_integrity_column()`, `test_flac_integrity()`, `update_integrity_result()`, `main()`
- tools/recommend_keepers.py: `ensure_decision_columns()`, `load_duplicate_groups()`, `compute_duration_delta()`, `extract_technical_quality()`, `decide_keeper()`, `write_report()`, `apply_decisions()`, `main()`
- tools/dupeguru_bridge.py: `ensure_similarity_column()`, `parse_dupeguru_csv()`, `load_decision_data()`, `apply_similarity_evidence()`, `main()`
- tools/integrity/scan.py: `scan()`
- tools/ingest/*: staging/promotion/reconcile entry points and helpers

## Restructuring Suggestions
- Consolidate scanning modes: expose `--metadata-only` and `--hash` phases to decouple heavy I/O.
- Standardise progress and verbosity across CLI subcommands.
- Move duplicate integrity logic from tools into `dedupe/core/integrity.py` for reuse.
- Unify DB access via `dedupe/storage` APIs; deprecate direct `sqlite3` usage in tools.
- Create a single pipeline script that orchestrates scan → match → manifest with configurable batch size and verbosity.
