# FLAC Deduplication System

A curator-first Python system for verifying, indexing, and auditing large FLAC collections recovered from heterogeneous sources.

**COMMUNE** is the future canonical library layout.  
**Yate** remains the metadata authority after ingestion.  
**The dedupe layer never deletes or mutates audio or tags.**  
It produces reviewable, resumable decisions only.

See **[docs/SYSTEM_SPEC.md](docs/SYSTEM_SPEC.md)** for the complete system specification.

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
zone_priority = ["accepted", "staging", "suspect", "quarantine"]
```

Yate is never invoked during scanning. Tag reading is passive only.

## Quick Start: Fast Deduplication Workflow

**Recommended**: Defer integrity checks until after deduplication to save time.

```bash
DB=~/Projects/dedupe_db/music.db

# 1. Fast scan (no integrity checks)
python3 tools/integrity/scan.py /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY \
  --db $DB --library recovery --zone accepted \
  --no-check-integrity --incremental --progress

# 2. Find duplicates and decide winners
python3 tools/decide/recommend.py --db $DB --output plan.json

# 3. Extract winner paths
cat plan.json | jq -r '.plan[].decisions[] | select(.action == "keep") | .path' > winners.txt

# 4. Verify winners only
python3 tools/integrity/scan.py /path/to/winners \
  --db $DB --check-integrity --recheck --progress
```

See **[docs/FAST_WORKFLOW.md](docs/FAST_WORKFLOW.md)** for the complete optimized workflow.

---

## Tools & Usage

### Multi-Source Integrity Scanning

Scan arbitrary sources into a single long-lived DB (resumable, multi-library aware):

```bash
# Primary recovered library
python3 tools/integrity/scan.py \
  /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY \
  --db ~/Projects/dedupe_db/music.db \
  --library recovery \
  --zone accepted \
  --check-integrity \
  --incremental \
  --progress \
  --verbose

# Older vault material
python3 tools/integrity/scan.py \
  /Volumes/Vault \
  --db ~/Projects/dedupe_db/music.db \
  --library vault \
  --zone suspect \
  --check-integrity \
  --incremental \
  --progress

# Known problematic sources
python3 tools/integrity/scan.py \
  /Volumes/bad \
  --db ~/Projects/dedupe_db/music.db \
  --library bad \
  --zone quarantine \
  --check-integrity \
  --incremental \
  --progress
```

**Nothing is copied. Nothing is renamed.**

### Decision Phase (Read-Only)

```bash
python3 tools/decide/recommend.py \
  --db ~/Projects/dedupe_db/music.db \
  --output plan.json
```

**Decision Logic (strict order):**
1. **Integrity**: Bitstream-valid files are preferred.
2. **Zone**: Accepted > Suspect > Quarantine.
3. **Quality**: Higher sample rate/bit depth is preferred.
4. **Provenance confidence**.

**Output:** JSON plan, human-readable explanations, no side effects.

## Development

* **Tests**: `pytest`
* **Type Checking**: `mypy dedupe tools`
* **Linting**: `flake8 dedupe tools`
