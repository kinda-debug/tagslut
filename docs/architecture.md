# Architecture overview

The modern `dedupe` package follows a modular layout that keeps scanning,
parsing, matching, and manifest generation responsibilities clearly separated.
All runtime entry points flow through the unified CLI which orchestrates the
underlying helpers.

```
+----------------------+       +-------------------+
|    dedupe.cli        | ----> |   dedupe.scanner  |
| argparse entry point |       +-------------------+
| sub-commands: scan,  | ----> +-------------------+
| parse, match,        | ----> | dedupe.rstudio_   |
| manifest             |       | parser            |
+----------+-----------+       +-------------------+
           |                       |
           v                       v
   +---------------+        +----------------+
   | dedupe.utils  | <----> | dedupe.metadata|
   +---------------+        +----------------+
           |                       |
           v                       v
   +---------------+        +-----------------------+
   | dedupe.matcher| <----> | dedupe.fingerprints   |
   +---------------+        +-----------------------+
           |
           v
   +----------------+
   | dedupe.manifest|
   +----------------+
```

## Module summary

- `dedupe.cli` – command routing, argument parsing, and logging.
- `dedupe.utils` – filesystem helpers, hashing, SQLite utilities, and shared
  helpers.
- `dedupe.metadata` – ffprobe/mutagen adapters that expose consistent metadata
  structures even when external binaries are unavailable.
- `dedupe.fingerprints` – Chromaprint integration with graceful fallbacks and
  similarity helpers.
- `dedupe.scanner` – library crawler that records metadata, tags, and optional
  fingerprints inside SQLite databases.
- `dedupe.rstudio_parser` – loader for R-Studio "Recognized Files" exports with
  automatic normalisation.
- `dedupe.matcher` – multi-signal comparison engine that correlates the library
  database with recovered candidates.
- `dedupe.manifest` – report generator that produces prioritised recovery
  manifests for downstream review.

## Legacy modules

Historical scripts, quarantine tooling, and bespoke sync utilities now live
under [`dedupe/ARCHIVE/`](../dedupe/ARCHIVE/). They remain available for audit
purposes but are no longer part of the supported runtime architecture. When in
need of old workflows, consult the archive alongside the README notes that
highlight modern replacements.
