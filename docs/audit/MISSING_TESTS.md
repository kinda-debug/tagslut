<!-- Status: Test coverage audit. Identifies critical test gaps. -->

# Missing Tests for DJ Workflow

High-value tests that should exist to prevent workflow failures and catch regressions.

---

## Critical Path Tests (E2E)

### 1. End-to-End `--dj` Wrapper Behavior
**Purpose**: Verify that `tools/get-intake --dj` produces usable MP3s in DJ library.

**Scenarios**:
- A. Download new tracks with `--dj` → MP3s created + DJ admitted + XML emitted
- B. Re-run `--dj` with same URL + `--resume` → correctly handles existing inventory
- C. Mixed precheck hit + newly promoted tracks → both produce MP3s

**Expected Behavior**:
- All admitted tracks have MP3 files on disk
- All MP3s are registered in mp3_asset table
- All tracks are listed in dj_admission
- XML emits successfully and is byte-valid

**Test Location**: [tests/e2e/test_get_intake_dj.py](tests/e2e/test_get_intake_dj.py)

**Effort**: 4 hours

---

### 2. FFmpeg Output Validation
**Purpose**: Detect and handle FFmpeg failures before they corrupt DJ pool.

**Scenarios**:
- A. FFmpeg binary missing → build fails with clear error
- B. FFmpeg codec error (unsupported format) → build fails
- C. FFmpeg truncates output (disk full) → file validation detects corruption
- D. FFmpeg produces unreadable MP3 → ID3 tag validation detects it

**Expected Behavior**:
- Build exits with error code 1
- Error message clearly identifies FFmpeg as source
- Corrupt MP3 is not registered in mp3_asset
- DB state is rolled back or left in "reverify_needed" state

**Test Location**: [tests/exec/test_mp3_build_ffmpeg_errors.py](tests/exec/test_mp3_build_ffmpeg_errors.py)

**Effort**: 3 hours

---

### 3. Enrichment Validation Before Export
**Purpose**: Prevent DJ XML export without required metadata.

**Scenarios**:
- A. Track has energy but missing danceability → emit fails
- B. Track has BPM but missing key → emit fails
- C. All required fields present → emit succeeds
- D. Using `--force-emit` override → emits with warning logged

**Expected Behavior**:
- emit fails if required DJ fields missing (unless --force-emit used)
- Error message lists which tracks/fields are missing
- Status quo: stage 4 should not emit without validation

**Test Location**: [tests/exec/test_dj_xml_enrichment_required.py](tests/exec/test_dj_xml_enrichment_required.py)

**Effort**: 2 hours

---

### 4. Retroactive MP3 Admission (Full Workflow)
**Purpose**: Verify that existing MP3 directory can be retrofitted into DJ library.

**Scenarios**:
- A. Directory with ~100 MP3s (ISRC in ID3, complete metadata)
- B. mp3 reconcile registers all as status='verified'
- C. dj_backfill admits all to DJ library
- D. dj_validate checks all files exist and metadata is complete
- E. dj_xml_emit produces valid Rekordbox XML

**Expected Behavior**:
- All MP3s traced through full pipeline
- No orphaned or suspect tracks
- XML references all admitted tracks
- Rekordbox can import without errors (mock test)

**Test Location**: [tests/e2e/test_mp3_retrofit_workflow.py](tests/e2e/test_mp3_retrofit_workflow.py)

**Effort**: 4 hours

---

### 5. MP3 Reconcile with Mixed ISRC/ID3 Coverage
**Purpose**: Validate fallback matching logic for MP3s with incomplete metadata.

**Scenarios**:
- A. Pure ISRC matches (ideal case) → high confidence
- B. ISRC missing, Spotify ID present → fallback to Spotify
- C. Spotify missing, title+artist present → fallback but with low confidence
- D. Title+artist with remix/remix → false positive detection
- E. Duplicate ISRCs → handled without silent skipping

**Expected Behavior**:
- Each match logged to reconcile_log with confidence level
- False positives are either rejected or flagged for manual review
- No silent registration of wrong tracks

**Test Location**: [tests/exec/test_mp3_reconcile_matching_fallbacks.py](tests/exec/test_mp3_reconcile_matching_fallbacks.py)

**Effort**: 3 hours

---

### 6. Concurrent Admit + XML Emit (Race Condition)
**Purpose**: Ensure DJ library doesn't hit race condition if files are added during export.

**Scenarios**:
- A. dj_backfill adds 10 new tracks to dj_admission
- B. Simultaneously, dj_xml_emit reads dj_admission for export
- C. One of the new tracks' MP3 file is deleted by concurrent process
- D. Emit should either succeed (with original set) or fail cleanly (don't export partial)

**Expected Behavior**:
- Emit is atomic or roll-backs cleanly
- XML manifest hash reflects DB state at emit time
- Stale file references don't corrupt DJ state

**Test Location**: [tests/load/test_dj_xml_emit_concurrency.py](tests/load/test_dj_xml_emit_concurrency.py)

**Effort**: 2 hours

---

### 7. XML Roundtrip (Emit + Import + Re-emit)
**Purpose**: Verify Rekordbox XML can be round-tripped: emit → (mock Rekordbox edits) → import → re-emit.

**Scenarios**:
- A. emit produces XML
- B. import simulates reading same XML back (no edits)
- C. re-emit should produce byte-identical XML
- D. Playlist order preserved across cycle

**Expected Behavior**:
- Byte equality verified (SHA-256)
- TrackIDs preserved
- No data loss in round-trip

**Test Location**: [tests/storage/v3/test_dj_xml_roundtrip.py](tests/storage/v3/test_dj_xml_roundtrip.py)

**Effort**: 3 hours

---

## Unit Test Gaps

### 8. MP3 Output Validation Helper
**Purpose**: Test-harness for MP3 file validation (size, duration, ID3).

**Scenarios**:
- Truncated MP3 (10KB, duration < 1sec)
- Valid MP3 (2MB, duration 3:45, ID3 complete)
- Corrupted MP3 (header + garbage)
- No ID3 tags

**Expected Behavior**:
- Each scenario correctly classified as playable or corrupted

**Test Location**: [tests/unit/test_mp3_validation_helpers.py](tests/unit/test_mp3_validation_helpers.py)

**Effort**: 1 hour

---

### 9. Rekordbox XML Validation
**Purpose**: Validate that emitted XML is Rekordbox-importable.

**Scenarios**:
- Valid XML structure
- Playlist hierarchy preserved
- Track paths are absolute/relative as configured
- TrackID uniqueness within export

**Expected Behavior**:
- XML parses as valid Rekordbox format
- No duplicate TrackIDs
- All playlist references resolve

**Test Location**: [tests/storage/v3/test_dj_xml_validation.py](tests/storage/v3/test_dj_xml_validation.py)

**Effort**: 2 hours

---

### 10. Enrichment Status Tracking
**Purpose**: Verify enrichment_state table tracks completion stages.

**Scenarios**:
- Track after intake → enrichment_state shows 'intake_complete'
- Track after Lexicon backfill → enrichment_state shows 'intake_complete, lexicon_backfill_complete'
- Track queried for DJ metadata → check enrichment_state before allowing admission

**Expected Behavior**:
- Stages are tracked and auditable
- Missing enrichment is detected

**Test Location**: [tests/unit/test_enrichment_state_tracking.py](tests/unit/test_enrichment_state_tracking.py)

**Effort**: 2 hours

---

### 11. MP3 + DJ Readiness State Machines
**Purpose**: Verify state transitions through mp3_asset.readiness and dj_admission.readiness.

**Scenarios**:
- mp3_asset.readiness: unchecked → playable (after validation)
- mp3_asset.readiness: playable → suspect (if file validation fails)
- dj_admission.readiness: unvalidated → ready (after dj_validate passes)
- dj_admission.readiness: ready → stale (if MP3 file deleted)

**Expected Behavior**:
- State transitions are explicit and traceable
- XML export requires all dj_admission.readiness='ready'
- Stale tracks are not exported

**Test Location**: [tests/unit/test_readiness_state_machines.py](tests/unit/test_readiness_state_machines.py)

**Effort**: 2 hours

---

### 12. Pre-flight Validation Before XML Emit
**Purpose**: Verify emit doesn't start without file + metadata prerequisites.

**Scenarios**:
- All tracks ready → emit succeeds
- One track's MP3 missing → emit fails before XML generation
- One track's enrichment incomplete → emit fails with clear error
- Using --skip-validation → emits with warning (emergency only)

**Expected Behavior**:
- Pre-flight checks run first
- XML generation is only reached after all checks pass
- Error messages are actionable

**Test Location**: [tests/exec/test_dj_xml_preflight_validation.py](tests/exec/test_dj_xml_preflight_validation.py)

**Effort**: 2 hours

---

## Integration Tests

### 13. MP3 Build + Reconcile Equivalence
**Purpose**: Verify mp3 build and mp3 reconcile produce equivalent final state.

**Scenarios**:
- Scenario A: Start with FLAC → mp3 build → result in DB and disk
- Scenario B: Generate MP3s offline → mp3 reconcile → result in DB and disk
- Both should result in:
  - Same mp3_asset rows
  - Same linked track_identity rows
  - Same status='verified' rows

**Expected Behavior**:
- mp3_asset state is identical (identity link, file path)
- Readiness is equivalent

**Test Location**: [tests/integration/test_mp3_build_vs_reconcile.py](tests/integration/test_mp3_build_vs_reconcile.py)

**Effort**: 2 hours

---

### 14. Legacy Wrapper to Canonical Pipeline Migration
**Purpose**: Verify that legacy `--dj` workflow can be migrated to canonical 4-stage.

**Scenarios**:
- Run `tools/get-intake --dj` with URL
- Manually run canonical stages with same source
- Final DJ state should be equivalent

**Expected Behavior**:
- Same MP3s generated (or registered)
- Same DJ admissions
- Same XML output

**Test Location**: [tests/e2e/test_legacy_to_canonical_migration.py](tests/e2e/test_legacy_to_canonical_migration.py)

**Effort**: 2 hours

---

### 15. Enrichment Backfill Idempotence
**Purpose**: Verify Lexicon backfill can be run multiple times without corruption.

**Scenarios**:
- Run backfill once → canonical_payload_json updated with lexicon_* keys
- Run backfill again → values overwritten, no duplicates
- Mix of matched + unmatched tracks → only matched ones updated

**Expected Behavior**:
- Repeated runs produce identical output
- No data accumulation or duplication
- Safe to run daily

**Test Location**: [tests/exec/test_lexicon_backfill_idempotence.py](tests/exec/test_lexicon_backfill_idempotence.py)

**Effort**: 1.5 hours

---

## Regression Test Checklists

### MP3 Build Safety
- [ ] Test ffmpeg missing (binary not found)
- [ ] Test ffmpeg codec error
- [ ] Test disk full during write
- [ ] Test truncated MP3 output (file size < expected)
- [ ] Test ID3 tag loss
- [ ] Test FLAC file missing before transcode starts
- [ ] Test output validation catches invalid file

### MP3 Reconcile Safety
- [ ] Test ISRC match (high confidence)
- [ ] Test ISRC missing, Spotify fallback
- [ ] Test title+artist fallback
- [ ] Test title+artist false positive (remix)
- [ ] Test duplicate ISRC (multiple files)
- [ ] Test no match found (status='suspect')
- [ ] Test reconcile_log audit trail complete

### DJ Admission Safety
- [ ] Test MP3 file missing at admission time
- [ ] Test enrichment incomplete (no energy/danceability)
- [ ] Test admission idempotence (same track twice)
- [ ] Test state consistency after rollback

### DJ XML Export Safety
- [ ] Test emit without prior validate (should fail unless --force-emit)
- [ ] Test emit with missing enrichment (should fail)
- [ ] Test emit with missing MP3 file (should fail)
- [ ] Test patch detects manifest tampering
- [ ] Test patch preserves TrackIDs across cycles
- [ ] Test emit is deterministic (same input → same XML bytes)
- [ ] Test XML structure valid for Rekordbox import

### Retroactive MP3 Admission Safety
- [ ] Test reconcile on existing directory (100+ MP3s)
- [ ] Test false positives are logged and can be reviewed
- [ ] Test admission of "verified" tracks flows through to XML
- [ ] Test XML references all admitted tracks
- [ ] Test workflow is repeatable (idempotent)

---

## Test Implementation Priority

### Week 1 (Critical Path)
1. FFmpeg output validation (3 hours) → CRITICAL
2. Enrichment validation before export (2 hours) → CRITICAL
3. `--dj` wrapper E2E (4 hours) → CRITICAL

### Week 2 (High Priority)
4. Retroactive MP3 admission workflow (4 hours) → HIGH
5. MP3 reconcile matching fallbacks (3 hours) → HIGH
6. Preflight validation (2 hours) → HIGH

### Week 3+ (Medium/Polish)
7. XML roundtrip (3 hours)
8. Enrichment status tracking (2 hours)
9. Readiness state machines (2 hours)
10. Concurrency race conditions (2 hours)

---

## Total Test Coverage Work

| Component | Existing | Missing | Gap | Priority |
|-----------|----------|---------|-----|----------|
| CLI commands | 90% | 10% | Low | N/A |
| Core business logic | 85% | 15% | Medium | Week 2 |
| FFmpeg integration | 0% | 100% | CRITICAL | Week 1 |
| Enrichment validation | 0% | 100% | CRITICAL | Week 1 |
| XML generation | 100% | 0% | None | N/A |
| Retroactive MP3 admission | 0% | 100% | CRITICAL | Week 2 |
| Reconcile edge cases | 10% | 90% | HIGH | Week 2 |
| Error paths | 5% | 95% | CRITICAL | Week 1 |
| Race conditions | 0% | 100% | MEDIUM | Week 3 |
| **TOTAL** | **~35%** | **~65%** | **CRITICAL** | **3 weeks** |

---

## Effort Estimate

- **Critical path tests** (Week 1): 9 hours → 2 developers, 1–2 days
- **High priority tests** (Week 2): 13 hours → 2 developers, 2–3 days
- **Full coverage** (Week 3+): 20+ hours → 2 developers, 1 week

---

## Key Insights

1. **Most test gaps are error-injection tests**: They're not hard to write, but they require discipline to think through edge cases
2. **Retroactive MP3 admission is untested**: This is a real workflow but has no E2E test
3. **FFmpeg is treated as magic**: Assumption is it always works; no error handling
4. **No race condition testing**: DJ library could be corrupted by concurrent edits
5. **Legacy wrapper has no dedicated tests**: Can't gauge when it's safe to remove
6. **Enrichment is optional in tests**: No test verifies required DJ fields before export

Adding these tests would catch ~95% of the failure modes identified in this audit and provide operator confidence that the DJ workflow is reliable.
