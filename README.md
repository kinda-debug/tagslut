# dedupe — audio recovery and reconciliation toolkit

This repository provides an end-to-end workflow for rebuilding large audio
libraries.  It consolidates library scanning, R-Studio export parsing,
fingerprint comparison, and manifest generation behind a single command line
interface.  Each workflow stage is exposed via a dedicated module inside the
`dedupe` package.

## Key capabilities

- **Library scanning** – Capture technical metadata, embedded tags, and optional
  Chromaprint fingerprints for every audio file in a collection.
- **Recovery parsing** – Ingest R-Studio "Recognized Files" exports into a
  structured SQLite database for repeatable analysis.
- **Matching engine** – Correlate recovered fragments with the canonical
  library, highlighting truncation, potential upgrades, and missing items.
- **Manifest generation** – Build a prioritised recovery manifest consumable by
  manual or automated restoration pipelines.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Unified CLI

All functionality is orchestrated by the `dedupe` command:

```bash
python3 -m dedupe.cli --help
```

Available sub-commands:

- `dedupe scan-library --root <path> --out library.db [--fingerprints]`
  Recursively scans an audio collection, writing metadata into a SQLite
  database.  The command records duration, bitrate, channel count, checksum, and
  optional Chromaprint fingerprints.
- `dedupe parse-rstudio --input recognized.txt --out recovered.db`
  Parses an R-Studio export, normalises file paths, and stores the results in a
  SQLite database.
- `dedupe match --library library.db --recovered recovered.db --out matches.csv`
  Produces a ranked set of recovery candidates by comparing filenames, file
  sizes, and other metadata.
- `dedupe generate-manifest --matches matches.csv --out manifest.csv`
  Converts match results into a prioritised manifest suitable for manual review
  or scripted restoration.

Every command accepts `--verbose` to enable detailed logging output.

## Global multi-volume recovery workflow

The new `scripts/global_recovery.py` entry point aggregates every available
volume, R-Studio export, and recovered fragment into a unified SQLite database.
The schema is purpose-built for cross-volume reconciliation:

- `global_files` – every scanned audio file with path, technical metadata, and
  optional Chromaprint fingerprint.
- `global_fragments` – R-Studio "Recognized Files" exports, stored once and
  re-parsed on re-runs without duplication.
- `global_resolved_tracks` – the resolver's latest decision for each normalised
  track group, including score, reason, and confidence value.

Typical workflow:

```bash
# 1. Scan every library root into a single database
python3 scripts/global_recovery.py scan \
    --root /Volumes/dotad/NEW_LIBRARY \
    --root /Volumes/Vault \
    --db artifacts/db/global_library.db \
    --resume --show-progress

# 2. Load any R-Studio Recognized*.txt exports
python3 scripts/global_recovery.py parse-recognized \
    "Recognized5_5 SanDisk Extreme 55AE 3008.txt" \
    --db artifacts/db/global_library.db

# 3. Resolve the best candidate per track and emit CSV reports
python3 scripts/global_recovery.py resolve \
    --db artifacts/db/global_library.db \
    --out-prefix artifacts/reports/global_recovery \
    --min-name-similarity 0.65 \
    --duration-tolerance 1.0 \
    --size-tolerance 0.02 \
    --threshold 0.55
```

The resolver writes four reports sharing the requested prefix:

- `*_keepers.csv` – canonical files to keep or restore.
- `*_improvements.csv` – higher-quality replacements identified across roots.
- `*_manual_repair.csv` – groups needing manual intervention or only fragments.
- `*_archive_candidates.csv` – obvious losers for quarantine or deletion.

Re-running any stage is safe: scans and fragment imports update rows in place,
and the resolver overwrites existing decisions with the most recent scores.

## Developer workflow

1. Run the unit tests to confirm the environment:

   ```bash
   pytest -q
   ```

2. Lint the project using `flake8`:

   ```bash
   flake8 dedupe
   ```

3. Execute the CLI locally to verify configuration:

   ```bash
   python3 -m dedupe.cli scan-library --root /path/to/library --out library.db --verbose
   ```

## Module overview

| Module | Purpose |
| ------ | ------- |
| `dedupe.utils` | Shared helpers for hashing, filesystem traversal, and SQLite management. |
| `dedupe.metadata` | ffprobe and tag extraction helpers with safe fallbacks. |
| `dedupe.fingerprints` | Chromaprint integration and similarity helpers. |
| `dedupe.scanner` | Library scanning pipeline producing SQLite records. |
| `dedupe.global_recovery` | Shared logic for the global multi-volume recovery workflow. |
| `dedupe.rstudio_parser` | Parser and loader for R-Studio exports. |
| `dedupe.matcher` | Matching heuristics combining filename, size, and quality signals. |
| `dedupe.manifest` | Manifest construction utilities for downstream recovery tools. |
| `dedupe.cli` | Unified command line interface wiring the modules together. |

## External dependencies

The toolkit expects the following external binaries when available:

- `ffprobe` / `ffmpeg` for metadata extraction and PCM hashing.
- `fpcalc` for Chromaprint fingerprints.

When the tools are missing the code gracefully degrades, recording whichever
metadata is available.  This allows offline planning using previously captured
SQLite databases.

## Documentation

Additional workflow documentation lives in:

- [`USAGE.md`](USAGE.md) – step-by-step operational notes.
- [`docs/`](docs/) – architecture diagrams and historical context.

Legacy tooling, experimental scripts, and prior prototypes have been archived
under [`dedupe/ARCHIVE/`](dedupe/ARCHIVE/) for historical reference. The new
package structure under `dedupe/` is the authoritative codebase; archived files
should not be modified except when adding context about their superseded
behaviour.

Contributions should update these documents whenever CLI behaviour or schemas
change.
