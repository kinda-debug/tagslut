# Recovery-First FLAC Deduplication

This repository is a recovery-first, evidence-preserving toolkit for scanning, auditing, and deduplicating large FLAC libraries. The workflow is **deterministic**, **resumable**, and **non-destructive** unless you explicitly approve changes.

## What You Work With

- `tools/` — operator CLIs (scan, decide, apply)
- `dedupe/` — core engine (integrity scan, matching, decisions)
- `docs/` — concise operator documentation

Scripts and one-off artifacts have been archived. Use the tools below.

## Core Features (Evidence-First)

- **Technical Provenance**: Tracks `checksum_type` (STREAMINFO vs SHA256) for every file.
- **Resource Guardrails**: Pre-flight disk space and write-sanity checks.
- **Adaptive Commits**: Time-based (60s) and batch-based database flushing.
- **Risk Profiling**: Automatic delta analysis (duration, bitrate, etc.) for duplicates.
- **High Performance**: Surgical indexing for fast queries on large datasets.

## Quickstart (V2)

1) Configure your environment:
   Copy `.env.example` to `.env` and update the paths.

2) Scan a root:
```bash
python3 -m dedupe scan /path/to/volume
```

3) Generate a plan:
```bash
python3 -m dedupe recommend --output plan.json
```

4) Apply decisions (moves to quarantine):
```bash
python3 -m dedupe apply plan.json --confirm
```

## Documentation

- **[GUIDE.md](GUIDE.md)** — Authoritative V2 operator guide and workflow.
- `COMPLEXITY_AUDIT.md` — Modernization roadmap and progress.
- `docs/` — Legacy documentation (being consolidated).
