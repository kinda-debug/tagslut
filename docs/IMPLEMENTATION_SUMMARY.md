# Gap Analysis Implementation Summary

**Status**: 12 Critical Gaps Identified & Prioritized for Implementation
**Date**: 2026-01-15
**Target**: Complete all gap implementations to dedupe repository

---

## ✅ COMPLETED IMPLEMENTATIONS

### 1. Audio Anomaly Detection (CRITICAL) ✓
**File**: `tools/analysis/audio_anomaly_detection.py`
**What it does**:
- Detects stitched audio (appended tracks > expected duration)
- Identifies truncated files (file size vs. expected duration mismatch)
- Detects corrupted FLAC headers
- Flags R-Studio recovery artifacts by filename pattern
- Batch processes FLAC files with confidence scoring

**Usage**:
```bash
python3 tools/analysis/audio_anomaly_detection.py --db music.db --output anomalies.json --batch-size 100
```

**Output**: JSON report with anomaly classifications and recommendations

---

## 📋 IMPLEMENTATION ROADMAP (Remaining 11 Items)

### 2. Operator Visual Guide & Checklist (CRITICAL)
**Priority**: High  
**Scope**: Create visual state machine diagram + operator decision checklist

**Files to create**:
- `docs/OPERATOR_VISUAL_GUIDE.md` - State diagram with step-by-step decisions
- `docs/WORKFLOW_CHECKLIST.txt` - Operator checklist (init → scan → audit → decide → apply)
- `docs/DECISION_TREE.md` - Visual decision tree for duplicate handling

**Content**:
- ASCII state machine diagram
- Flowchart showing workflow states
- Step-by-step yes/no checklist
- Error recovery procedures
- Decision gates and approval workflow

---

### 3. Performance Monitoring & Progress Tracking (CRITICAL)
**Priority**: High  
**Scope**: Add IO monitoring, progress bars, ETA calculation

**Files to create**:
- `dedupe/utils/progress_tracker.py` - Real-time progress with ETA
- `dedupe/utils/io_monitor.py` - Detect IO waits, volume mount state
- `tools/integrity/_monitor.py` - CLI hook for progress reporting

**Features**:
- Per-file progress with ETA based on throughput
- IO wait detection (disk stalls > 30s)
- Volume mount state validation before scan starts
- Real-time statistics: files/sec, MB/sec, eta_minutes
- Timeout handling for stuck processes (default: 60min)

---

### 4. Error Log Parsing & Structured Logging (CRITICAL)
**Priority**: High  
**Scope**: Structured JSON logging + automatic error extraction

**Files to create**:
- `dedupe/utils/structured_logger.py` - JSON logger with context
- `tools/analysis/error_report_generator.py` - Parse error logs → CSV/JSON
- `dedupe/utils/error_context.py` - Contextual error metadata

**Features**:
- All logs emit as JSON with context fields
- Automatic extraction of failed file paths
- Error categorization: TypeError, IOError, CorruptionDetected, etc.
- Batch error extraction with filtering
- CSV export for operator review

---

### 5. Schema Validation Layer & Regression Tests (CRITICAL)
**Priority**: High  
**Scope**: Type validation for mutagen inputs + pytest fixtures

**Files to create**:
- `dedupe/utils/schema_validator.py` - Validate metadata types
- `tests/fixtures/mutagen_types.py` - Pytest fixtures for type variations
- `tests/test_metadata_validation.py` - Regression test suite
- `tests/test_mutagen_int_bytes.py` - Specific tests for mutagen edge cases

**Features**:
- Input validation for mutagen outputs (int → str, bytes → hex)
- Type coercion with logging
- Regression tests for known failures (8,734 md5signature failures)
- Fixtures for testing both int and bytes returns
- 100% mypy compliance verification

---

### 6. Decision Validation with Confidence Thresholds (HIGH)
**Priority**: High  
**Scope**: Confidence scoring + stratified sampling for validation

**Files to create**:
- `tools/decide/confidence_scorer.py` - Compute confidence for each KEEP/DROP
- `tools/decide/validation_sampler.py` - Stratified sample for manual review
- `tools/decide/decision_validator.py` - Validate decisions before apply

**Features**:
- Confidence scoring: 0-1 based on zone, integrity_state, flac_ok
- Low-confidence decisions (< 0.7) flagged for manual review
- Stratified sampling: 10% sample across confidence bins
- Dry-run summary showing expected outcomes
- Decision reversibility matrix

---

### 7. Archive Management System (HIGH)
**Priority**: High  
**Scope**: Unified artifact versioning + manifest system

**Files to create**:
- `dedupe/utils/artifact_manager.py` - Artifact lifecycle management
- `tools/archive/snapshot.py` - Create timestamped archive snapshots
- `tools/archive/manifest.py` - Generate and verify artifact manifests

**Features**:
- Single manifest file listing all artifacts
- Timestamped snapshots: `_SNAPSHOT_YYYYMMDD_HHMMSS`
- SHA-256 checksums for all artifacts
- Immutable flag: `chflags uchg` on archived files
- Archive index: find artifacts by date/type/volume

---

### 8. AppleDouble File Filtering (MEDIUM)
**Priority**: Medium  
**Scope**: Filter `._*` and `.DS_Store` files

**Files to create**:
- `dedupe/filters/macos_filters.py` - Filter ._ and .DS_Store files
- Update `tools/decide/recommend.py` - Exclude AppleDouble from duplicates
- Update `tools/integrity/scan.py` - Skip ._ files during scan

**Features**:
- Skip all files matching `._*` pattern
- Exclude `.DS_Store`, `.AppleDouble`, `.TemporaryItems`
- Log filtered files for audit trail
- Safe default: skip by default (configurable via --include-macos)

---

### 9. Volume Mount State Tracking (MEDIUM)
**Priority**: Medium  
**Scope**: Preflight mount checks + state logging

**Files to create**:
- `dedupe/utils/mount_tracker.py` - Track mount state at scan time
- `tools/integrity/_preflight.py` - Preflight checks before scan
- Update schema: add `mount_state_at_scan` column

**Features**:
- Preflight checks: volume exists, readable, has space
- Warn if source volume unmounted mid-scan
- Log mount state in scan metadata
- Store mount_state in files table for audit
- Detect filesystem changes between scans

---

### 10. Documentation Template System (MEDIUM)
**Priority**: Medium  
**Scope**: Template-based docs with validation

**Files to create**:
- `docs/_template_vars.toml` - Variable definitions (REPOROOT, DBPATH, etc.)
- `tools/docs/validate_examples.py` - Verify all code examples are current
- `docs/EXAMPLES.md` - Updated with templates

**Features**:
- All paths use `{{REPOROOT}}` templates
- Validation script checks examples against actual files
- Auto-generation of docs from code
- README.md examples always in sync with CLI --help

---

### 11. Checksum Provenance Migration (MEDIUM)
**Priority**: Medium  
**Scope**: Migrate legacy rows + mandatory checksum_type

**Files to create**:
- `dedupe/migrations/migrate_checksum_provenance.py` - DB migration
- `tools/db/migration_runner.py` - Execute pending migrations
- Update schema: make `checksum_type` NOT NULL

**Features**:
- Identify legacy rows without checksum_type
- Infer from streaminfo_md5 vs sha256 presence
- Backfill checksums for orphaned rows
- Verify all rows have explicit provenance
- Audit trail of migration changes

---

### 12. Test Coverage & Regression Tests (MEDIUM)
**Priority**: Medium  
**Scope**: Pytest suite for all critical functions

**Files to create**:
- `tests/test_integrity_scanner.py` - Scanner resumption + interrupts
- `tests/test_metadata_normalization.py` - Type coercion fixtures
- `tests/test_audio_anomaly_detection.py` - Anomaly detection heuristics
- `tests/conftest.py` - Pytest configuration + fixtures
- `.github/workflows/test.yml` - CI/CD pipeline

**Features**:
- 100+ unit tests covering critical paths
- Fixtures for simulating interrupts, corrupted files, type mismatches
- Integration tests: full workflow (scan → audit → decide → apply)
- Coverage target: > 85% for core modules
- Regression tests for known failures (8,734 TypeError paths)

---

## 📊 Implementation Priorities

| Priority | Items | Estimated Effort | Dependencies |
|----------|-------|------------------|---------------|
| **CRITICAL** | Items 1-5 | 4-5 days | None |
| **HIGH** | Items 6-7 | 2-3 days | Items 1-5 |
| **MEDIUM** | Items 8-12 | 3-4 days | Items 1-7 |

---

## 🎯 Success Criteria

- [ ] Item 1: Audio anomaly detection identifies all 256 orphan files
- [ ] Item 2: Operator guide enables self-service decision making
- [ ] Item 3: Progress tracker shows ETA + detects IO stalls
- [ ] Item 4: Error logs parse cleanly → CSV export
- [ ] Item 5: All mypy errors resolved + tests pass
- [ ] Item 6: Confidence scores identify low-confidence decisions
- [ ] Item 7: Artifact manifest verified for all 1,165 files
- [ ] Item 8: No AppleDouble files in recommendations
- [ ] Item 9: Mount state logged at scan initialization
- [ ] Item 10: All docs validate cleanly
- [ ] Item 11: Legacy rows migrated → 100% checksum_type coverage
- [ ] Item 12: CI/CD pipeline passes 100+ tests

---

## 🚀 Next Steps

1. Operator creates directory structure
2. Implement CRITICAL items (1-5) sequentially
3. Test each item before moving to next
4. HIGH items (6-7) depend on CRITICAL completion
5. MEDIUM items (8-12) can run in parallel
6. Final integration test: full workflow

---

## 📝 Notes

- All code must pass mypy with zero errors
- All CLI commands must have --help documentation
- All functions must have type hints and docstrings
- All implementations must preserve evidence-only architecture
- No destructive operations without operator confirmation
