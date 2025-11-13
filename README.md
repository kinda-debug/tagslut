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

Contributions should update these documents whenever CLI behaviour or schemas
change.
