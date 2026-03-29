# CODEX_AGENT.md

## Repository role
tagslut is a CLI-first Python project for building and managing DJ-ready music libraries.

Preserve existing behavior unless a task explicitly changes it.

## Canonical command
The only supported CLI entrypoint is:

poetry run tagslut

The `dedupe` alias has been removed. Do not reference it.

## Current architecture highlights

### Storage
The project uses the v3 identity model with SQLite via the v3 migration runner.

Active migration chain (applied in this order):

- 0006: track_identity phase 1 (provider columns, merged_into_id, indexes)
- 0007: phase 1 column renames
- 0009: chromaprint fingerprint support
- 0010: provider uniqueness - beatport, tidal, qobuz, spotify (partial indexes)
- 0011: provider uniqueness hardening - apple_music, deezer, traxsource
- 0012: ingestion provenance - ingested_at, ingestion_method, ingestion_source,
  ingestion_confidence (all NOT NULL, five-tier CHECK constraint)

track_identity provenance fields are NOT NULL. Every insert must supply:

- ingested_at: ISO 8601 UTC, set once, never updated
- ingestion_method: controlled vocabulary - see docs/INGESTION_PROVENANCE.md
- ingestion_source: specific evidence string
- ingestion_confidence: verified | corroborated | high | uncertain | legacy

Do not touch tagslut/storage/v3/schema.py without a migration file.

Fresh DB path:  /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db
Legacy DB path: /Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db

(legacy is read-only archaeology - do not write to it)

### DJ pipeline

Canonical path:

FLAC (MASTER_LIBRARY)
-> tagslut intake process-root --phases identify,enrich,art,promote,dj
-> tagslut dj pool-wizard
-> tagslut dj xml emit -> Rekordbox XML

Use only v3-safe phases on a v3 DB: identify, enrich, art, promote, dj.
Do not use legacy scan phases (register, integrity, hash) on a v3 DB.

Key DJ commands:

- tagslut dj pool-wizard: Build final MP3 DJ pool from MASTER_LIBRARY
- tagslut dj backfill: Auto-admit all verified MP3s
- tagslut dj validate: Verify DJ library state
- tagslut dj xml emit: Generate Rekordbox XML

DJ candidate export (read-only, produces CSV):

`make dj-candidates V3=<db> OUT=<csv>`

Implemented in scripts/dj/export_candidates_v3.py

### Credentials

Token storage: ~/.config/tagslut/tokens.json (single source of truth).
tokens.json takes precedence over env vars. Env var fallback logs a warning.

CLI:

- `tagslut auth token-get <provider>`: Print access token for shell capture
- tagslut auth status: Show auth status for all providers

Shell scripts must use:

`TOKEN=$(tagslut auth token-get beatport 2>/dev/null)`

Not: source env_exports.sh (removed from harvest scripts).

Full credential model: docs/CREDENTIAL_MANAGEMENT.md

## Working rules

- start from failing command or test
- inspect minimal code surface
- prefer small reversible patches
- avoid repo-wide refactors
- avoid touching database files unless required
- do not use `git push --force` or `git filter-repo` - operator-only procedures
- do not run the full test suite during implementation. targeted pytest only: `poetry run pytest tests/<specific_module> -v`
- full suite (`poetry run pytest tests/ -x -q`) is permitted only as a final gate immediately before merging a PR, and only when the prompt says so explicitly

## Tests

Prefer targeted pytest runs over the full suite.
