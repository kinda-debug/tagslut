# Consolidated Scanner Architecture

## Status: Simplified (2026-01-05)

The dedupe repository has been consolidated to remove duplicate scanning systems.

---

## Current Production Scanners

### 1. **`tools/integrity/scan.py`** + **`dedupe/integrity_scanner.py`**
**Purpose**: Multi-source FLAC scanning into the `files` table  
**Schema**: Modern integrity schema (multi-library, multi-zone)  
**Use cases**:
- Fast metadata extraction (no integrity checks)
- Optional `flac -t` verification
- Incremental/resumable scans
- Multi-library aggregation

**CLI**:
```bash
python3 tools/integrity/scan.py /path/to/library \
  --db artifacts/db/music.db \
  --library recovery \
  --zone accepted \
  --no-check-integrity \
  --incremental \
  --progress
```

### 2. **`dedupe/scanner.py`**
**Purpose**: Legacy library scanner into `library_files` table  
**Status**: Kept for backward compatibility  
**Used by**: Original `dedupe` CLI  
**Schema**: Legacy unified schema (includes fingerprints, dup_group, duplicate_rank)

---

## Archived Scanners

### **`tools/archive/ingest/run.py`** (Step-0 Pipeline)
**Status**: Archived (superseded by tools/integrity/scan.py)  
**Reason**: Duplicated functionality with added complexity  
**Features** (now unused):
- Tiered hashing (prehash shortcuts)
- Separate provenance tables (`audio_content`, `integrity_results`, `canonical_map`)
- Decision/artifact indexing
- Explicit outcome classification (CANONICAL, REDUNDANT, REACQUIRE, TRASH)

**Replacement workflow**:
```bash
# Old: tools/ingest/run.py scan + decide + apply
# New: tools/integrity/scan.py + tools/decide/recommend.py
```

---

## Utility Libraries

### **`dedupe/step0.py`**
**Purpose**: Shared utility functions for ingestion pipelines  
**Status**: Active (used by tools and tests)  
**Exports**:
- `sanitize_component()` — Safe filename generation
- `classify_integrity()` — Parse `flac -t` output
- `extract_identity_hints()` — Extract ISRC/MusicBrainz IDs
- `build_canonical_path()` — Construct canonical paths
- `choose_canonical()` — Select best file from duplicates
- `confidence_score()` — Estimate reacquire confidence

**Used by**: Any code that needs tag parsing, path sanitization, or integrity classification.

---

## Decision Engine

### **`tools/decide/recommend.py`**
**Purpose**: Analyze duplicates and recommend actions  
**Inputs**: `files` table from `artifacts/db/music.db`  
**Outputs**: JSON plan with zone-aware decisions  
**CLI**:
```bash
python3 tools/decide/recommend.py \
  --db artifacts/db/music.db \
  --output plan.json
```

---

## Recommended Workflow

See [docs/FAST_WORKFLOW.md](../FAST_WORKFLOW.md):

1. **Fast scan** (no integrity) → `tools/integrity/scan.py --no-check-integrity`
2. **Cluster duplicates** → `tools/decide/recommend.py`
3. **Extract winners** → `jq` filter on plan.json
4. **Verify winners only** → `tools/integrity/scan.py --check-integrity --recheck`

This minimizes expensive `flac -t` verification by only checking files you'll actually keep.

---

## Summary

| Component | Status | Purpose |
|-----------|--------|---------|
| `tools/integrity/scan.py` | **Active** | Primary production scanner |
| `dedupe/integrity_scanner.py` | **Active** | Core scanning logic |
| `dedupe/scanner.py` | **Active** | Legacy scanner (backward compat) |
| `dedupe/step0.py` | **Active** | Shared utility functions |
| `tools/decide/recommend.py` | **Active** | Decision engine |
| `tools/archive/ingest/run.py` | **Archived** | Superseded Step-0 pipeline |

---

**No more duplicate scanning systems. One clear path forward.**
