# Repository Audit Report

**Status**: Clean  
**Last Updated**: 2026-01-05  
**Refactor**: 2025 Architecture Stabilization

---

## Summary

This repository implements a curator-first FLAC deduplication system with:
- **Non-destructive** decision-making (no auto-deletes)
- **Multi-source** integrity scanning (resumable, library/zone-aware)
- **Centralized** SQLite schema via `dedupe/storage/schema.py`
- **Layered** architecture (core → storage → utils → tools)

All generated artifacts have been cleaned. Legacy scripts archived. Schema initialization centralized. Zero behavior regressions.

See **[docs/SYSTEM_SPEC.md](docs/SYSTEM_SPEC.md)** for the complete system specification.

---

## Repository Structure

```
dedupe/           # Core package (hashing, integrity, decisions, metadata)
├── core/         # Business logic (no I/O)
├── storage/      # SQLite schema, queries, models
├── utils/        # Shared utilities (parallel, config, logging)
├── db/           # Legacy schema re-exports (for backward compatibility)
└── external/     # Picard/Yate integration

tools/            # Operational CLIs
├── integrity/    # Integrity scanning (multi-source, resumable)
├── decide/       # Decision engine (recommend, apply)
├── ingest/       # Step-0 ingestion pipeline
└── review/       # Manual review helpers

scripts/          # Maintenance helpers
├── python/       # Python utilities
├── shell/        # Shell utilities
└── archive/      # Legacy scripts (historical reference)

docs/             # Active documentation
├── examples/     # Example artifacts
├── plans/        # Recovery/cleanup plans
└── archive/      # Historical snapshots

tests/            # Unit/integration tests
├── core/         # Core logic tests
├── storage/      # Storage layer tests
└── data/         # Test fixtures

artifacts/        # Runtime output (gitignored except placeholders)
├── db/           # SQLite databases
├── logs/         # Scan/integrity logs
└── tmp/          # Temporary files
```

---

## Key Files

### Configuration
- `config.toml` — Runtime configuration (zones, library roots, decision rules)
- `config.example.toml` — Example config template
- `pyproject.toml` — Packaging and dependencies

### Core Package
- **`dedupe/storage/schema.py`** — **Canonical** SQLite schema definitions
- `dedupe/scanner.py` — Library scanner (delegates to `storage.schema`)
- `dedupe/integrity_scanner.py` — Multi-source integrity scanner
- `dedupe/core/hashing.py` — Tiered hashing strategies
- `dedupe/core/decisions.py` — Decision scoring logic
- `dedupe/core/metadata.py` — Integrity-aware metadata extraction

### Tools
- **`tools/integrity/scan.py`** — **Primary scanner CLI** (multi-library, resumable, optional integrity checks)
- **`tools/decide/recommend.py`** — **Decision engine** (duplicate clustering, zone-aware recommendations)
- `tools/decide/apply.py` — Plan executor
- `tools/archive/ingest/` — Archived Step-0 tiered-hashing pipeline (superseded)

### Documentation
- **`docs/SYSTEM_SPEC.md`** — Complete system specification
- `docs/architecture.md` — Architecture overview
- `docs/step0_pipeline.md` — Step-0 ingestion details
- `README.md` — Quick start and usage

---

## Audit Results

### ✅ Kept (Active)
All source files, tests, docs, and operational scripts are retained and aligned with the 2025 architecture refactor.

### 🗄️ Archived
- `scripts/archive/populate_refractor.py` — Legacy script with destructive helpers
- `tools/archive/ingest/` — Step-0 tiered-hashing pipeline (superseded by tools/integrity/scan.py)
- `docs/archive/status/*.md` — Historical status snapshots (superseded)

### 🗑️ Deleted (Generated/Redundant)
- `flac_dedupe.egg-info/` — Build artifacts
- `out/` — Generated report outputs
- `runs/` — Generated run outputs
- `**/__pycache__/` — Python bytecode cache
- `.output.txt` — Generated output artifact
- `dedupe/core/actions.py` — Unused deletion helper (contradicts non-destructive policy)

---

## Schema Consolidation

**Before**: Duplicate schema definitions in `dedupe/db/schema.py` and `dedupe/scanner.py`  
**After**: Single canonical source in `dedupe/storage/schema.py`

`dedupe/scanner.initialise_database()` now delegates to `dedupe.storage.schema.initialise_library_schema()` for backward compatibility.

---

## Zero Behavior Regressions

✅ Scanning remains resumable and incremental  
✅ Existing DBs remain valid (additive migrations)  
✅ Existing scans can continue (no CLI changes)  
✅ Integrity semantics unchanged  
✅ Decision logic unchanged  

---

## Next Steps

See [docs/SYSTEM_SPEC.md](docs/SYSTEM_SPEC.md) for:
- Multi-source scanning workflow
- Decision phase usage
- Performance guarantees
- Artifact indexing
