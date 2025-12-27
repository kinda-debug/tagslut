# Repository Structure

This repository is organised around a single Python package, `dedupe`, plus a small set of operational tools, documentation, and test assets. The layout below reflects the cleaned structure and package boundaries.

## Top-level layout

- `dedupe/` — Main application package containing the CLI, scanning, matching, health scoring, and recovery logic.
- `tools/` — Operational scripts packaged for import (`db_upgrade`, `manual_ingest`, `move_to_hrm`).
- `scripts/` — Shell/Python helpers used during maintenance and data patching.
- `docs/` — Architecture notes, playbooks, and guides.
- `tests/` — Automated unit tests and fixtures.
- `artifacts/` — Runtime outputs; structured with `db/`, `logs/`, `manifests/`, and `tmp/` for collected data.
- `archive/` and `dedupe/ARCHIVE/` — Legacy materials retained for reference only.

## Package overview (`dedupe`)

- `cli.py` — Entry point wiring subcommands for scanning, matching, manifest generation, health scoring, deduplication, HRM relocation, and DB upgrades.
- `db/` — Schema helpers (`schema.py`) centralising the `library_files` definition.
- `scanner.py` — Library scanner and ingest pipeline writing metadata to SQLite.
- `matcher.py` — Correlates scanned library entries with recovered metadata exports.
- `manifest.py` — Builds recovery manifests from match CSVs with prioritisation rules.
- `health_score.py` — Detailed FLAC health scoring with mutagen-based checks.
- `healthscore.py` — Lightweight, read-only scoring for quick CLI evaluation.
- `healthcheck.py` — Validates FLAC files using `flac --test` and tag completeness heuristics.
- `fingerprints.py` — Chromaprint integration helpers and similarity utilities.
- `metadata.py` — FFprobe/mutagen probing helpers returning structured metadata.
- `utils.py` — Shared helpers for hashing, path normalisation, SQLite access, and I/O utilities.
- `deduper.py` — Marks canonical files in the library database and emits duplicate reports.
- `hrm_relocation.py` — Moves healthy, canonical files into the HRM folder layout with manifest output.
- `global_recovery.py` — Cross-root recovery and resolution workflow for reconciled datasets.
- `rstudio_parser.py` — Parses R-Studio recovery exports into the recovered files schema.
- `ARCHIVE/` — Deprecated legacy scripts kept for historical context.

## Tools

- `tools/db_upgrade.py` — Upgrades legacy per-volume databases into the unified schema.
- `tools/manual_ingest.py` — Helper for manually ingesting files into the database.
- `tools/move_to_hrm.py` — Utility for relocating canonical files to HRM storage.

## Tests and fixtures

- `tests/` contains unit tests covering the scanner, health scoring, matching, CLI wiring, HRM relocation, and database upgrade paths. Fixtures live alongside tests in the `data/` directory where applicable.

## Documentation and plans

- `README.md`, `USAGE.md`, `docs/` — User and operator guidance.
- `cleanup_plan.md` — Proposed removals and deprecated assets.
- `FILE_ANALYSIS.md` — File-by-file commentary on current assets and status.

This structure ensures import safety, centralises the schema definition, and makes package responsibilities clear without changing existing behaviour.
