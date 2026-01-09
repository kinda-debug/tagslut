# Recovery-First FLAC Deduplication

This repository is a recovery-first, evidence-preserving toolkit for scanning, auditing, and deduplicating large FLAC libraries. The workflow is **deterministic**, **resumable**, and **non-destructive** unless you explicitly approve changes.

## What You Work With

- `tools/` — operator CLIs (scan, decide, apply)
- `dedupe/` — core engine (scanner, matcher, decisions)
- `docs/` — concise operator documentation

Scripts and one-off artifacts have been archived. Use the tools below.

## Core Features (Evidence-First)

- **Technical Provenance**: Tracks `checksum_type` (STREAMINFO vs SHA256) for every file.
- **Resource Guardrails**: Pre-flight disk space and write-sanity checks.
- **Adaptive Commits**: Time-based (60s) and batch-based database flushing.
- **Risk Profiling**: Automatic delta analysis (duration, bitrate, etc.) for duplicates.
- **High Performance**: Surgical indexing for fast queries on large datasets.

## Quickstart (Minimal)

1) Set your DB path (once):

```toml
# config.toml
[db]
path = "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db"
```

2) Scan a root (resumable, verbose by default):

```bash
python3 tools/integrity/scan.py /Volumes/RECOVERY_TARGET/Root
```

3) Generate a decision plan (read-only):

```bash
python3 tools/decide/recommend.py --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" --output plan.json
```

4) Apply decisions only after review:

```bash
python3 tools/decide/apply.py --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" --plan plan.json
```

## Docs (Start Here)

- `docs/OPERATOR_GUIDE.md` — tailored recovery workflow
- `docs/SCANNING.md` — resumable scanning behavior and defaults
- `docs/TOOLS.md` — what each CLI does
- `docs/CONFIG.md` — minimal config for this workflow
- `docs/ARTIFACTS.md` — where evidence outputs live
