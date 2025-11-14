# Tooling reference

This repository now revolves around the unified `dedupe` CLI. The sections
below summarise the active commands, supporting modules, and where to find
archived tooling for historical context.

## Active commands

| Command | Purpose | Key outputs |
| ------- | ------- | ----------- |
| `dedupe scan-library --root <path> --out library.db [--fingerprints]` | Recursively index an audio library, collecting filesystem metadata, ffprobe stream data, optional Chromaprint fingerprints, and embedded tags. | SQLite database with `library_files` table |
| `dedupe parse-rstudio --input recognized.txt --out recovered.db` | Parse an R-Studio "Recognized Files" export and normalise row data. | SQLite database with `recovered_files` table |
| `dedupe match --library library.db --recovered recovered.db --out matches.csv` | Compare scanned library entries with recovered candidates using filename similarity, size deltas, and optional fingerprint data. | CSV match report |
| `dedupe generate-manifest --matches matches.csv --out manifest.csv` | Transform the matcher output into a prioritised manifest with operator notes and recovery statuses. | CSV manifest |

All commands accept `--verbose` to surface detailed logging during long-running
operations.

## Supporting modules

- `dedupe.utils` – hashing helpers, filesystem traversal, SQLite context
  manager, and common type conversions.
- `dedupe.metadata` – ffprobe/mutagen adapters that return consistent metadata
  structures even when dependencies are unavailable.
- `dedupe.fingerprints` – Chromaprint integrations and similarity helpers with
  graceful fallbacks.
- `dedupe.scanner` – batching logic that writes metadata into SQLite with
  resumable commits.
- `dedupe.rstudio_parser` – robust CSV/TSV ingestion for R-Studio exports.
- `dedupe.matcher` – matching heuristics that balance filename similarity and
  size tolerance.
- `dedupe.manifest` – manifest writer that adds priorities and notes based on
  match classifications.

## Legacy scripts

The former collection of bespoke scripts (duplicate planners, quarantine
inspectors, deep health scanners, etc.) has been moved to
[`dedupe/ARCHIVE/`](../dedupe/ARCHIVE/). They remain unchanged to preserve past
investigations and historical context. When referencing older documentation that
mentions files within `scripts/`, look for a counterpart inside the archive.
Consider porting reusable logic into the modern modules before reviving a legacy
workflow.
