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

- `dedupe scan-library --root <path> --out library.db --resume`
  Recursively scans an audio collection, writing metadata into a SQLite
  database.  The command records duration, bitrate, channel count, checksum, and
  filename heuristics by default.  Append `--fingerprints` to request optional
  Chromaprint extraction when `fpcalc` is available.
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

### Recommended scan workflows

- **Default library scan** – fingerprints skipped, fastest path:

  ```bash
  dedupe scan-library --root /path/to/library --out library.db --resume
  ```

- **Optional fingerprint scan** – only when you need mastering-level
  differentiation and `fpcalc` is present:

  ```bash
  dedupe scan-library --root /path/to/library --out library.db --resume --fingerprints
  ```

  Fingerprints are generated only for files missing them when `--resume` is
  supplied, allowing incremental updates.

### Fingerprinting is optional

Chromaprint fingerprints enhance matching when two files share identical size
and duration but differ in mastering.  They are not required for dedupe,
recovery identification, truncation detection, or library reconciliation.  When
`--fingerprints` is omitted or `fpcalc` is unavailable, the scanner falls back
to checksum → duration → bitrate → filename similarity heuristics without
logging warnings.

- `fpcalc` must be on `PATH` to enable fingerprints.  When missing, scans
  continue normally without attempting extraction.
- `--resume` skips unchanged files using a size and modification-time check.
  During a resumed scan with `--fingerprints`, only files lacking fingerprints
  are refreshed.

### Working across multiple volumes

A single SQLite database can hold metadata for several volumes.  For example:

```bash
dedupe scan-library --root /Volumes/dotad --out library.db --resume
dedupe scan-library --root /Volumes/Vault --out library.db --resume
dedupe scan-library --root /Volumes/sad --out library.db --resume
```

The commands may be re-run at any time; unchanged files are skipped and newly
added files are appended to the shared database.

### Example workflows

1. **Scan multiple volumes into one database**

   ```bash
   dedupe scan-library --root /Volumes/dotad --out library.db --resume
   dedupe scan-library --root /Volumes/Vault --out library.db --resume
   dedupe scan-library --root /Volumes/sad --out library.db --resume
   ```

2. **Inspect recently indexed files**

   ```bash
   sqlite3 library.db "SELECT path, size_bytes, duration FROM library_files ORDER BY mtime DESC LIMIT 10;"
   ```

3. **Match recoveries without fingerprints**

   ```bash
   dedupe match --library library.db --recovered recovered.db --out matches.csv
   ```

4. **Fingerprint-only refresh** (after an initial scan)

   ```bash
   dedupe scan-library --root /path/to/library --out library.db --resume --fingerprints
   ```

   Existing entries retain metadata; missing fingerprints are generated when
   `fpcalc` is available.

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

> **Developer note** – Fingerprint extraction lives in `dedupe.fingerprints` and
> is invoked via `dedupe.scanner.prepare_record`.  The helper
> `dedupe.scanner.resolve_fingerprint_usage` centralises the logic that decides
> whether Chromaprint runs.  Extensions that add new fingerprint behaviour
> should call this helper so users who skip `--fingerprints` continue to receive
> the checksum/duration/bitrate/filename heuristics without side effects.

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
