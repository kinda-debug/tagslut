# File-by-file analysis

## Root
- `README.md`, `USAGE.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `LICENSE` — Project documentation and metadata.
- `pyproject.toml`, `requirements.txt`, `poetry.lock`, `MANIFEST.in` — Packaging and dependency definitions.
- `config.toml`, `config.example.toml` — Runtime configuration examples.
- `Makefile` — Convenience commands for linting/testing.
- `scripts/python/dd_flac_dedupe_db.py` — **Deprecated** standalone dedupe script; superseded by the packaged workflows.
- `tmp_dedupe_patch.patch`, `tmp_full_patch_no_pyc.patch`, `tmp_missing.patch` — Temporary patch artifacts (cleanup recommended).
- `patches/` — Patch lists used during migrations; review for removal once obsolete.
- `artifacts/` — Output area with `db/`, `logs/`, `manifests/`, and `tmp/` subdirectories for runtime data.
- `archive/legacy_root/` — Historical assets retained for reference.
- `scripts/` — Maintenance helpers plus `scripts/shell/` and `scripts/python/` for legacy root scripts.
- `tools/` — Operational utilities for duplicate review, integrity checking, and decision automation:
  - **Duplicate review workflow**: `export_dupe_groups.py`, `open_dupe_pair.sh`, `listen_dupes.sh`
  - **Decision engine**: `recommend_keepers.py`, `review_needed.sh`, `dupeguru_bridge.py`
  - **Integrity checking**: `scan_flac_integrity.py`, `find_corrupt_flacs.sh`
  - **Database utilities**: `db_upgrade.py`, `manual_ingest.py`, `move_to_hrm.py`

## Package: `dedupe`
- `__init__.py` — Aggregates core modules for package-wide import convenience.
- `cli.py` — CLI wiring for scanning, matching, manifest generation, health scoring, deduplication, HRM relocation, and DB upgrades.
- `db/schema.py` — Central definition of `library_files` schema and initializer; exported via `dedupe.db`.
- `scanner.py` — Scans libraries into SQLite with optional fingerprinting, resume logic, and batch upserts.
- `matcher.py` — Matches scanned library entries to recovered metadata and writes CSV reports.
- `manifest.py` — Builds recovery manifest CSVs from match outputs with prioritisation and notes helpers.
- `health_score.py` — Mutagen-backed FLAC health scoring that reports metrics and clamps scores.
- `healthscore.py` — Lightweight, read-only scoring helper used by the CLI.
- `healthcheck.py` — Runs `flac --test`/mutagen checks plus tag completeness heuristics; returns structured results.
- `fingerprints.py` — Chromaprint integration (availability checks, fingerprint generation, similarity scoring).
- `metadata.py` — FFprobe/mutagen probing utilities returning structured metadata objects.
- `utils.py` — Shared helpers for path normalisation, hashing, chunking, SQLite access, JSON handling, and context managers.
- `deduper.py` — Marks canonical files within `library_files` and optionally writes duplicate reports.
- `hrm_relocation.py` — Relocates healthy, canonical files into the HRM hierarchy with checksum validation and manifest output.
- `global_recovery.py` — Global recovery workflow for multi-root scans, fragment resolution, and report generation.
- `rstudio_parser.py` — Parses R-Studio exports into the `recovered_files` schema for matching.
- `healthscore.py`, `health_score.py`, `healthcheck.py` — Parallel health scoring utilities with different scopes (read-only scoring vs. mutagen/`flac` validation).
- `ARCHIVE/` — **Deprecated** legacy scripts retained for historical reference; not part of active workflows.

## Tests
- `tests/` — Unit tests covering scanner, matcher, manifest, CLI, health scoring, HRM relocation, DB upgrades, metadata utilities, and repository structure. Fixtures reside under `tests/data/`.

This analysis reflects the current organisation after cleanup and highlights deprecated assets for potential removal.
