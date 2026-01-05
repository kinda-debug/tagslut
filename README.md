# FLAC Deduplication System

A curator-first Python system for verifying, reporting, and auditing large FLAC music libraries.
COMMUNE is the canonical library layout, Yate is the metadata source of truth,
and the dedupe layer only produces reviewable reports (never auto-deletes).

## Architecture

This repository has been refactored (2025) into a clean, layered architecture:

* **`dedupe/core/`**: Pure business logic (Hashing, Metadata, Integrity, Decisions).
* **`dedupe/storage/`**: SQLite persistence layer with additive migrations.
* **`dedupe/utils/`**: Shared utilities (Parallelism, Config, Logging).
* **`tools/`**: Command-line interfaces (CLIs) for user interaction.

## Installation

Requires Python 3.11+.

```bash
pip install -r requirements.txt
# OR
poetry install
```

## Configuration

Copy `config.example.toml` to `config.toml` or `~/.config/dedupe/config.toml`.
You can also point to a specific config file with `DEDUPE_CONFIG=/path/to/config.toml`.

```toml
[library]
name = "COMMUNE"
root = "/Volumes/COMMUNE"

[library.zones]
staging = "10_STAGING"
accepted = "20_ACCEPTED"

[decisions]
zone_priority = ["accepted", "staging"]
```

Yate is the source of truth for metadata in COMMUNE. The dedupe tooling reads
tags in `20_ACCEPTED` but will not mutate them.

## Tools & Usage

### Step-0 Canonical Ingestion
Scans arbitrary input directories, validates FLAC integrity (`flac --test`),
resolves duplicates, and produces a plan for canonical promotion.

```bash
python tools/ingest/run.py scan \
  --inputs /Volumes/recovery_source_1 /Volumes/recovery_source_2 ~/Downloads/flac \
  --canonical-root /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY \
  --quarantine-root /Volumes/RECOVERY_TARGET/Root/QUARANTINE \
  --db artifacts/db/music.db \
  --library-tag recovery-2025-01 \
  --zone recovery \
  --strict-integrity \
  --progress
```

Additional Step-0 subcommands:

```bash
# Build a plan from existing scan tables.
python tools/ingest/run.py decide --db artifacts/db/music.db \
  --canonical-root /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY \
  --quarantine-root /Volumes/RECOVERY_TARGET/Root/QUARANTINE \
  --library-tag recovery-2025-01

# Apply a saved plan JSON.
python tools/ingest/run.py apply --plan plan.json

# Summarize scan progress.
python tools/ingest/run.py status --db artifacts/db/music.db

# Index artifacts (audit reports, legacy databases, .DOTAD_* markers).
python tools/ingest/run.py artifacts --inputs /Volumes/RECOVERY_TARGET/Root/artifacts \
  --db artifacts/db/music.db
```

See `docs/step0_pipeline.md` for the full Step-0 specification and example outputs.

### 1. Scan & Verify Integrity
Scans a library, verifies FLAC integrity (`flac -t`), calculates SHA-256 hashes, and upserts to the DB.

```bash
python3 tools/integrity/scan.py /Volumes/Music/FLAC --db artifacts/db/music.db --check-integrity
```

To tag the scanned paths as a zone (staging or accepted):

```bash
python3 tools/integrity/scan.py /Volumes/COMMUNE/10_STAGING --db artifacts/db/music.db --library COMMUNE --incremental --progress
```

### 2. Find Duplicates & Recommend Actions
Analyzes the database for duplicates and generates a JSON report for curator review.

```bash
python3 tools/decide/recommend.py --db artifacts/db/music.db --output plan.json
```

**Decision Logic (Review-First):**
1.  **Integrity**: Bitstream-valid files are preferred.
2.  **Zone**: Accepted is preferred over staging for reference.
3.  **Quality**: Higher sample rate/bit depth is preferred.

## Development

* **Tests**: `pytest`
* **Type Checking**: `mypy dedupe tools`
* **Linting**: `flake8 dedupe tools`
