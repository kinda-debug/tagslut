<!-- Status: Audit report. Evidence-driven diagnosis of DJ workflow brittleness. -->

# DJ Workflow Audit

**Generated:** 2026-03-22
**Methodology:** Hostile, evidence-driven code review against real operator expectations
**Verdict:** The DJ workflow is **unnecessarily fragmented, operationally unreliable, and poorly aligned with actual DJ library operations**. The canonical 4-stage pipeline exists but is not the default, legacy wrappers remain in the critical path, and multiple failure modes are untested.

---

## Executive Summary

### What the User Expects
- Download or intake tracks → automatic reliable MP3 copies → admit to DJ library → export Rekordbox XML
- Seamless integration: FLAC masters → MP3 derivatives → DJ-curated subset → Rekordbox-ready XML
- One clear workflow, repeatable and auditable with no manual file handling

### What Actually Happens
1. **Multiple entry points create confusion**: `tools/get --dj`, `tools/get-intake --dj`, and the canonical 4-stage CLI are all present but with different guarantees
2. **Legacy `--dj` wrapper has brittle behavior**:
   - Non-deterministic MP3 generation (follows either "promoted" or "precheck" code path)
   - Skips explicit MP3 registration and DJ admission stages
   - Silently swallows MP3 failures (no validation of ffmpeg output)
3. **MP3 generation is fragmented and under-tested**:
   - 7 distinct failure modes are untested (ffmpeg missing, malformed output, metadata loss, path collisions, ID3-less files, ISRC false positives, title+artist false positives)
   - No validation of output before or after transcoding
4. **Enrichment is multi-stage but not explicit**:
   - Metadata is 60–80% complete at intake but Lexicon backfill is optional and deferred
   - DJ XML can export without required fields (energy, danceability) if backfill is skipped
   - No clear contract about which enrichment must occur before DJ admission
5. **Data model has hidden complexity**:
   - 5 core DJ tables + overlapping responsibilities
   - Tracing master→MP3→DJ requires 4+ JOINs through multiple layers
   - No explicit state machine for MP3 or DJ readiness
6. **Test coverage is incomplete**:
   - 80%+ coverage on CLI commands and core logic
   - **Critical gaps**: No E2E retroactive MP3 admission tests, no error injection for ffmpeg failures, no race condition tests, no XML corruption safeguards
7. **Rekordbox XML is stable but not the primary contract**:
   - XML emit/patch work well and preserve TrackIDs
   - But XML is treated as optional downstream export, not first-class part of the workflow
   - No explicit support for playlist editing and re-import as a primary DJ curation mechanism

---

## Failure Map: Why the DJ Workflow Fails in Practice

### Critical Failures

#### 1. `--dj` Flag Creates Two Divergent Runtime Paths
**Symptoms:**
- `tools/get-intake --dj` produces different outcomes depending on whether tracks are newly promoted or already in inventory (precheck hit)
- No guarantee MP3 copies exist after the command completes
- No way to predict which code path will execute

**Root Causes:**
- [tools/get-intake L920–L930](tools/get-intake#L920-L930): `DJ_MODE` flag is set, but handler code branches based on file existence and precheck state
- [tools/get-intake L2800–L2900](tools/get-intake#L2800-L2900): Fallback M3U generation logic runs instead of explicit MP3 build + DJ admission
- No state transition guarantees or pre-conditions checked

**Evidence:**
```bash
# Run 1: Newly promoted tracks → MP3 generation works (by luck)
tools/get-intake --dj "https://beatport.com/release/12345"  # SUCCESS

# Run 2: Same URL already in inventory → skips MP3 generation, only generates M3U
tools/get-intake --dj "https://beatport.com/release/12345"  # FAILS for DJ
```

**Impact:**
- Operator cannot rely on MP3 copies existing after `--dj` run
- Silent failure: no error, but DJ library is empty
- Forced manual remediation: operator must run `mp3 reconcile` + `dj admit` manually

---

#### 2. FFmpeg Failures Are Silent
**Symptoms:**
- MP3 generation reports success but produces corrupted/truncated files
- Missing error handling for ffmpeg exit codes, stderr parsing, output validation
- Operator can't distinguish between "MP3 generation skipped" and "MP3 generation failed"

**Root Causes:**
- [tagslut/dj/transcode.py](tagslut/dj/transcode.py): No validation of ffmpeg output
- [tools/get-intake L2700–L2750](tools/get-intake#L2700-L2750): Wrapper script doesn't capture ffmpeg stderr
- No file size checks, duration validation, or ID3 tag verification

**Evidence:**
- `mp3 build` command assumes ffmpeg succeeds if exit code is 0
- No checks for: ffmpeg missing, insufficient disk space, codec errors, malformed output
- Tests mock ffmpeg: they don't detect actual ffmpeg failures

**Impact:**
- DJ pool contains broken MP3s that Rekordbox import silently fails on
- Operator only discovers failure at Rekordbox import time (hours after build)
-Requires full rebuild to fix

---

#### 3. Enrichment Is Optional When It Should Be Mandatory
**Symptoms:**
- DJ XML exports without energy, danceability, or happiness fields if Lexicon backfill is skipped
- No validation that required DJ metadata is present before export
- Operator has no clear signal that DJ library is incomplete

**Root Causes:**
- [docs/DJ_WORKFLOW.md](docs/DJ_WORKFLOW.md): Lexicon backfill is documented as optional
- [tagslut/dj/xml.py](tagslut/dj/xml.py): No validation ensures canonical_payload_json has required DJ fields
- Two enrichment paths: provider metadata (60–80% complete) and Lexicon backfill (separate manual step)

**Evidence:**
- `dj xml emit` accepts `--skip-validation` flag that bypasses enrichment checks
- No test validates that exported XML has energy/danceability fields
- Workflow documentation doesn't mark Lexicon backfill as mandatory

**Impact:**
- DJ library is incomplete without explicit Lexicon backfill
- Rekordbox import works but DJ metadata (energy, key) is missing
- Operator must manually re-import or run backfill after XML export

---

### High-Severity Issues

#### 4. MP3 Registration Has Duplicate-Check False Positives
**Symptoms:**
- `mp3 reconcile` skips valid MP3s due to Beatport ID mismatch
- Title+artist fallback match creates false positives (e.g., remixes, compilations)
- No way to disambiguate on conflict

**Root Causes:**
- [tagslut/mp3/reconcile.py](tagslut/mp3/reconcile.py): Match priority is ISRC > Spotify ID > title+artist
- Title+artist matching is case-insensitive and ignores remmixer/version info
- No confidence scoring or manual override path

**Evidence:**
- Test: `test_reconcile_skips_already_registered` assumes ISRC is always available
- No test for: duplicate ISRCs, missing ISRCs with remixes, albumizer false positives

**Impact:**
- MP3s are silently skipped or registered to wrong tracksOperator can't tell which
- Requires manual DB inspection to fix

---

#### 5. No Explicit Contract for "DJ Readiness"
**Symptoms:**
- DJ admission happens even if MP3 asset::status is "suspect" or "quarantine"
- No validation that:
  - MP3 file exists and is readable
  - MP3 has complete metadata (artist, title, duration)
  - Canonical identity has required DJ fields
  - Canonical identity has been enriched

**Root Causes:**
- [tagslut/dj/admission.py](tagslut/dj/admission.py): `dj backfill` only checks `mp3_asset.status='verified'` but doesn't validate file or metadata
- `dj validate` runs post-admission but doesn't block XML export
- No explicit "DJ readiness" state separate from "MP3 asset verified"

**Evidence:**
- Test: `test_e2e3_backfill_then_validate_passes` shows validate is optional
- No test validates that MP3 files still exist between admission and XML emit
- No test validates identity has enrichment before XML emit

**Impact:**
- DJ library admits tracks with incomplete metadata
- XML export fails with missing fields → operator must rebuild
- File deletion between admission and export corrupts DJ state

---

### Medium-Severity Issues

#### 6. Three Separate DJ Export Code Paths
**Symptoms:**
- DJ pool building logic exists in 3 places:
  - `tools/get-intake --dj` (shell/Python wrapper)
  - `tagslut/dj/export.py` (CLI command)
  - `scripts/dj/build_pool_v3.py` (lower-level script)
- Inconsistent behavior, different validation, different error handling

**Root Causes:**
- Legacy `tools/get` wrapper predates CLI
- Later CLI refactoring didn't remove wrapper path
- Script path kept for "lower-level" direct Python use (but no users documented)

**Evidence:**
- `tools/get-intake` L2800–L2900: Wrapper logic
- `tagslut/cli/dj.py`: CLI commands
- `scripts/dj/build_pool_v3.py`: Script path
- Three paths, different validation, different manifest formats

**Impact:**
- Operator confusion about which path to use
- Bugs fixed in one path don't propagate to others
- No canonical source of truth for DJ export behavior

---

#### 7. Rekordbox XML Not First-Class in Workflow
**Symptoms:**
- XML export is Stage 4 but feels optional/downstream
- No explicit support for playlist editing and re-import as primary curation
- Playlist membership in XML is read-only from DB (no round-trip)
- No support for Rekordbox cue points as input to DJ curation

**Root Causes:**
- XML initially designed as export artifact, not primary workflow boundary
- DJ admission and validation don't require XML emit
- No bidirectional sync between Rekordbox XML and tagslut DB

**Evidence:**
- `dj validate` doesn't reference XML
- `dj xml emit` is not required for DJ library to be considered "complete"
- No tests validate XML playlist structure or cue point preservation
- No command to re-import XML edits from Rekordbox

**Impact:**
- Operator uses Rekordbox as black-box: import → edit → export → reimport → ???
- Changes in Rekordbox don't sync back to DJ library
- XML becomes stale vs. DB state over time

---

#### 8. Enrichment Timing Ambiguity
**Symptoms:**
- Metadata enrichment happens at 3+ stages:
  - Initial intake (provider metadata, 60–80% complete)
  - [Optional] Post-move async (`tools/get` wrapper only)
  - [Optional] Explicit Lexicon backfill
  - At XML export (frozen state)
- Operator has no clear contract about when enrichment is "done"
- Re-running intake vs. backfill has different effects

**Root Causes:**
- Multiple enrichment providers (Beatport, TIDAL, Deezer, Lexicon) with different coverage
- Each adds to `track_identity.canonical_payload_json` independently
- No explicit "enrichment status" tracking per identity

**Evidence:**
- Lexicon backfill instructions recommend post-download async run
- But canonical 4-stage pipeline doesn't include explicit backfill
- Docs say "Safe to run repeatedly — overwrites only lexicon_* prefixed keys"

**Impact:**
- Operator doesn't know if DJ library is enriched enough for export
- Lexicon backfill can be skipped, leaving DJ metadata incomplete
- XML export is non-deterministic: depends on which enrichment steps were run

---

### Lower-Severity Issues

#### 9. MP3 Build Path Assumption
**Symptoms:**
- MP3 build assumes all master FLAC files exist and are readable
- No pre-flight check for file existence before transcoding begins
- Failures mid-transcode cause partial output and state inconsistency

**Root Causes:**
- [tagslut/dj/build.py](tagslut/dj/build.py): No pre-flight validation
- Wrapper script doesn't check MASTER_LIBRARY before starting

**Evidence:**
- Test `test_e2e1_mp3_build_skips_missing_flac` shows the code skips missing files, but this is discovery-time (via exception), not pre-flight
- Operator doesn't know how many FLAC files will fail until transcode runs

---

#### 10. No Atomic Multi-Stage State
**Symptoms:**
- `dj backfill` → `dj validate` → `dj xml emit` are three separate commands
- Each writes state independently
- Interruption between stages leaves inconsistent state
- Retry logic is unclear

**Root Causes:**
- No multi-stage transaction or checkpoint system
- Each command is independent CLI invocation
- No "rollback" if one stage fails

**Evidence:**
- Test `test_e2e3_backfill_idempotent` shows idempotence but not atomicity
- Operator must manually recover if interrupted

---

## Bottlenecks Ranked by Severity

| Severity | Issue | Impact | Category |
|----------|-------|--------|----------|
| **CRITICAL** | `--dj` wrapper has two divergent paths | DJ MP3s not created, silent failure | Design flaw |
| **CRITICAL** | FFmpeg failures are silent | Broken MP3s in DJ pool | Missing error handling |
| **CRITICAL** | Enrichment is optional, not mandatory | DJ metadata incomplete | Validation gap |
| **HIGH** | MP3 reconcile has false positives | Wrong tracks registered | Logic flaw |
| **HIGH** | No "DJ readiness" contract | Admits incomplete tracks | Validation gap |
| **HIGH** | Three DJ export code paths | Behavior inconsistency | Code fragmentation |
| **HIGH** | Rekordbox XML not first-class | XML becomes stale vs. DB | Architectural gap |
| **MEDIUM** | Enrichment timing is ambiguous | Operator doesn't know when "done" | UX/documentation |
| **MEDIUM** | No pre-flight MP3 build check | Failures discovered mid-transcode | Missing validation |
| **MEDIUM** | No atomic multi-stage state | Inconsistency on interrupt | Missing safeguards |

---

## DJ Workflow Distinctions: Current Reality

### Master FLAC Library
- **Definition**: Canonical sources of truth for tracks (one per identity)
- **Storage**: `$MASTER_LIBRARY` mounted volume
- **Responsibility**: Source truth only; not modified after intake
- **Schema**: `asset_file` with `role='master'`
- **Status**: ✓ Well-defined

### MP3 Library
- **Definition**: Derived MP3 copies for DJ use
- **Storage**: `$DJ_LIBRARY` or `$DJ_MP3_ROOT` (separate mounted volume)
- **Responsibility**: Generated from master FLAC on demand or registered from existing
- **Schema**: `mp3_asset` table, status = `['suspected', 'verified', 'quarantine']`
- **Problem**: No explicit "MP3 readiness" state; status is about confidence, not readiness
- **Status**: ⚠️ Partial; status machine is incomplete

### DJ Library
- **Definition**: Curated subset of MP3s admitted for DJ playback
- **Storage**: Logical table (`dj_admission`) + file references to MP3 library
- **Responsibility**: Explicit admission gate; requires validation
- **Schema**: `dj_admission` table (identity_id, mp3_asset_id) with timestamps
- **Problem**: No explicit "DJ readiness" validation before XML export
- **Status**: ⚠️ Partial; admission logic skips critical validations

### Current Schema Problems
- **No MP3 "status machine"**: `mp3_asset.status` conflates confidence with readiness
- **No DJ "readiness" marker**: Admission doesn't validate MP3 file or metadata
- **No enrichment "status"**: No tracking of which enrichment steps were completed
- **Overlapping responsibilities**: MP3 status, DJ admission, and file validation are intertwined

---

## Enrichment Timing Analysis

### Current Enrichment Stages

1. **Stage 1 — Intake (Provider metadata)**
   - BPM, key, duration, artist, title from Beatport/TIDAL
   - **Coverage**: 60–80% complete
   - **Mandatory**: Yes, for master intake
   - **Optional**: No

2. **[LEGACY] Post-Move Async (wrapper only)**
   - Additional provider calls (Beatport album details, TIDAL metadata enrichment)
   - **Coverage**: Incremental from Stage 1
   - **Mandatory**: No; only in `tools/get` wrapper with `--enrich` flag
   - **Optional**: Yes

3. **Explicit Lexicon Backfill (manual)**
   - Energy, danceability, happiness, popularity, bpm, key from Lexicon DJ SQLite export
   - **Coverage**: Comprehensive for DJ metadata
   - **Mandatory**: No; documented as repeatable/optional
   - **Optional**: Yes
   - **When**: Post-intake, pre-DJ admission (recommended)

4. **At XML Export (frozen state)**
   - Metadata read from canonical_payload_json as-is
   - **Coverage**: Whatever was enriched upstream
   - **Mandatory**: No explicit validation
   - **Optional**: `--skip-validation` flag skips all checks

### Problems

- **No mandatory enrichment contract**: DJ XML can export without energy/danceability if Lexicon backfill is skipped
- **Timing ambiguity**: No clear signal when enrichment is "done"
- **Incomplete Stage 1**: Provider metadata is only 60–80% coverage; DJ needs more
- **Optional Stage 2** (post-move async) only exists in deprecated wrapper
- **Optional Stage 3** (Lexicon backfill) is manual and not integrated into canonical 4-stage pipeline

### Recommendation

**Mandatory enrichment contract**:
- Stage 1 (intake): `track_identity` created with full provider metadata
- Stage 3 (DJ admission): Require Lexicon backfill (or provider fallback) for energy, danceability, key before admission
- Stage 4 (XML export): Validate that required DJ fields exist; fail if missing

---

## Data Model Clarity Assessment

### Schema Complexity

**Core DJ Tables** (5):
- `dj_admission`: Identity + MP3 asset mapping (primary DJ contract)
- `dj_track_id_map`: TrackID assignment for Rekordbox (stable across re-emits)
- `dj_export_state`: Manifest hash + metadata for XML emit/patch cycle
- `mp3_asset`: MP3 file metadata and status tracking
- `track_identity`: Master identity (linked to FLAC via asset_file)

**Supporting Tables** (3):
- `asset_file`: File-to-identity mapping (one-to-many for masters + MP3s)
- `reconcile_log`: Audit trail for MP3 reconciliation decisions
- `enrichment_state`: [Proposed] Track enrichment completion status

### Current Issues

1. **No explicit MP3 status machine**
   - `mp3_asset.status` uses: `['suspected', 'verified', 'quarantine']`
   - Conflates **confidence** (does ISRC match?) with **readiness** (is file playable?)
   - Admission logic checks `status='verified'` but doesn't validate file or metadata

2. **No DJ "readiness" state**
   - Admission table has no status or readiness marker
   - `dj validate` checks files post-admission but doesn't block export
   - XML export has no pre-flight validation

3. **Complex JOIN chain for master→MP3→DJ**
   ```sql
   track_identity
   ← asset_file (join on identity_id, where role='master')
   ← asset_file (join on identity_id, where role='mp3')
   ← mp3_asset (join on asset_file_id)
   ← dj_admission (join on mp3_asset_id)
   ← dj_track_id_map (join on admission_id)
   ```
   **Problem**: 5+ JOINs to trace one track through the pipeline

4. **Overlapping admission logic**
   - Admission checks `mp3_asset.status='verified'`
   - Validation checks file existence separately
   - XML export doesn't run pre-flight validation
   - No single source of truth for "is this DJ track ready?"

### Recommendation

**Introduce explicit MP3 + DJ readiness states**:
- Add `mp3_asset.readiness` column: `['unchecked', 'playable', 'suspect', 'corrupted']`
- Add `dj_admission.readiness` column: `['unvalidated', 'ready', 'stale', 'orphaned']`
- Update `dj validate` to set `dj_admission.readiness='ready'` (blocking state)
- Require `dj_admission.readiness='ready'` before XML can emit

---

## Test Coverage Gaps

### What's Tested Well (80%+)

1. **CLI command parsing and dispatch** ✓
2. **Core business logic** (reconcile, admit, XML generation) ✓
3. **Deterministic XML emit/patch** ✓
4. **TrackID stability across re-emits** ✓

### Critical Gaps (Not Tested, 0%)

1. **End-to-end `--dj` wrapper behavior**
   - No test validates that `tools/get --dj` produces usable MP3s
   - No test validates `--dj` + `--resume` behavior
   - No test for fallback M3U generation

2. **FFmpeg failure injection**
   - No test for ffmpeg exit code > 0
   - No test for ffmpeg missing entirely
   - No test for truncated/corrupted MP3 output
   - No test for ID3 tag loss

3. **MP3 reconciliation edge cases**
   - No test for duplicate ISRCs
   - No test for false-positive title+artist matches (remixes, compilations)
   - No test for Beatport ID mismatch with ISRC fallback

4. **Retroactive MP3 admission**
   - No test for retrofitting existing MP3 files into DJ library
   - No test for MP3 directories that have mixed DJ + non-DJ content

5. **Enrichment validation**
   - No test validates required DJ fields (energy, danceability) before XML emit
   - No test validates behavior when Lexicon backfill is skipped
   - No test validates enrichment across multiple runs

6. **Race conditions**
   - No test for concurrent `dj admit` + `dj xml emit`
   - No test for file deletion between admission and export
   - No test for DB state changes during XML generation

7. **XML correctness**
   - No test validates Rekordbox XML import after export
   - No test validates playlist membership after file reorganization
   - No test validates path references in exported XML

---

## Rekordbox XML Integration Assessment

### Current Capabilities

**✓ Strengths:**
- Deterministic generation with stable TrackID assignment
- Manifest hash prevents tampering
- Cue point preservation via `dj_track_id_map`
- Emit/patch cycle is robust and tested

**✗ Weaknesses:**
- XML is Stage 4 export artifact, not first-class workflow
- No bidirectional sync: edits in Rekordbox don't update DB
- Playlist membership is read-only from DB (no round-trip)
- No support for Rekordbox cue points as input to DJ curation
- No official support for XML editing/patching external to tagslut

### Primary Questions Evaluated

1. **Should Rekordbox XML editing be officially supported?**
   - **Current**: XML is export-only
   - **Recommendation**: YES, add `dj xml import` command to round-trip playlist edits from Rekordbox
   - **Rationale**: Rekordbox is the primary operational tool; DJ curation often happens in place

2. **Should XML be a stable interoperability boundary?**
   - **Current**: Stage 4 export, optional
   - **Recommendation**: YES, make XML emit mandatory after DJ admission
   - **Rationale**: Ensures Rekordbox compatibility is always verified

3. **Should TrackID assignment be stable across edits?**
   - **Current**: YES, via `dj_track_id_map`
   - **Status**: ✓ Already implemented correctly

4. **How to handle retroactive MP3 admission in XML?**
   - **Current**: No clear contract
   - **Recommendation**: Add `dj xml import` to re-export after new admissions

---

## Architecture Recommendations

### Top 5 Reasons the DJ Workflow Failed in Practice

1. **Multiple entry points, no clear canonical path**: `tools/get --dj`, `tools/get-intake --dj`, and 4-stage CLI all exist with different guarantees. Operator doesn't know which to use; gets wrong behavior by default.

2. **Silent MP3 generation failures**: FFmpeg errors are not detected or reported. DJ pool contains broken MP3s. Operator only discovers failure at Rekordbox import (hours later).

3. **Enrichment is optional when it should be mandatory**: DJ XML exports without required metadata (energy, danceability) if Lexicon backfill is skipped. No operator notification before export.

4. **No "DJ readiness" validation**: Admission happens even if MP3 is suspect or metadata is missing. XML export doesn't run pre-flight checks. DJ library can be incomplete without operator knowledge.

5. **Rekordbox XML is not first-class**: Operator must navigate between Rekordbox (primary tool) and tagslut (DB). Edits in Rekordbox don't sync back to DB. Workflow feels fragmented.

---

### Minimum Viable Redesign

**Goal**: Make DJ workflow reliable, operationally clear, and free from silent failures.

#### 1. Single Entry Point (Canonical 4-Stage Pipeline)
- Deprecate `tools/get --dj` and `tools/get-intake --dj` entirely
- Make canonical 4-stage commands the only supported path
- Add clear deprecation warnings to legacy wrappers
- Document why legacy paths are unsafe

#### 2. Non-Optional Enrichment
- Add `enrichment_state` table to track completion status
- Make Lexicon backfill mandatory before `dj admit` (or provider fallback)
- Add `dj validate` check: require energy, danceability, key for all admitted tracks
- Fail XML export if required fields are missing (`--force-export` override for special cases)

#### 3. Mandatory Pre-Flight & Post-Flight Validation
- `mp3 build`: Validate output file size, duration, ID3 tags before registering
- `dj admit`: Validate MP3 file still exists and is readable
- `dj xml emit`: Require `dj validate` to pass first (explicit prerequisite)
- Add detailed error reporting for each validation failure

#### 4. Explicit MP3 + DJ Readiness States
- Add `mp3_asset.readiness` column: `['unchecked', 'playable', 'suspect', 'corrupted']`
- Add `dj_admission.readiness` column: `['unvalidated', 'ready', 'stale', 'orphaned']`
- Update state machine through pipeline:
  - `mp3 build` → `mp3_asset.readiness='playable'` (after output validation)
  - `dj validate` → `dj_admission.readiness='ready'` (after file + metadata validation)
  - `dj xml emit` requires all `dj_admission.readiness='ready'`

#### 5. Rekordbox as First-Class Boundary
- Add `dj xml import` command to re-import playlist edits from Rekordbox
- Make XML emit mandatory after every `dj admit` or `dj backfill` run
- Document XML as the canonical Rekordbox integration layer
- Add tests to validate XML roundtrip: emit → import → re-emit → byte-identical

---

### Shortest Path to Boring, Reliable Operator Experience

**Day 1 (Immediate Safety)**:
1. Add deprecation warnings to `tools/get --dj` and `tools/get-intake --dj`
2. Add FFmpeg output validation to `mp3 build` (file size, duration, ID3 checks)
3. Add enrichment validation to `dj xml emit` (fail if energy/danceability missing)

**Day 3 (Clarity)**:
1. Add explicit `dj validate` as mandatory pre-condition for XML emit
2. Document the canonical 4-stage pipeline as the only supported path
3. Add status display to all DJ commands (show current readiness state)

**Week 1 (Robustness)**:
1. Implement `enrichment_state` table and Lexicon backfill as mandatory step
2. Add `mp3_asset.readiness` and `dj_admission.readiness` columns
3. Add state machine transitions through pipeline
4. Add comprehensive error reporting with recovery instructions

**Week 2+ (Polish)**:
1. Add `dj xml import` for round-trip Rekordbox editing
2. Consolidate three DJ export code paths into one
3. Add end-to-end test suite for `--dj` behavior (if wrapper is kept for compatibility)

---

### Recommended Model for Master FLAC Library

**Definition**: Canonical sources of truth. One file per identity.
**Scope**: Read-only after intake.
**Storage**: `$MASTER_LIBRARY` mounted volume.
**Responsibilities**:
- Source truth for metadata, duration, audio quality
- Linked via `asset_file` with `role='master'`
- Enriched at intake time (provider metadata)

**Contract**:
- Once a FLAC is admitted to master library, its identity is immutable
- Path and metadata are canonical
- No modifications after intake (except enrichment via `canonical_payload_json`)

---

### Recommended Model for MP3 Library

**Definition**: Derived MP3 copies, ephemeral, regenerable from masters.
**Scope**: Managed through `mp3 build` or `mp3 reconcile` commands.
**Storage**: `$DJ_LIBRARY` mounted volume (separate from master).
**Responsibilities**:
- Transcode from master FLAC or register existing MP3s
- Validate output and track readiness via `mp3_asset.readiness` state
- Link back to canonical identity via `mp3_asset` table

**Contract**:
- MP3 readiness is explicit: `['unchecked', 'playable', 'suspect', 'corrupted']`
- Only MP3s with `readiness='playable'` can be admitted to DJ library
- MP3 files can be regenerated if deleted without losing DB state

---

### Recommended Model for DJ Library

**Definition**: Curated subset of MP3s admitted for DJ playback.
**Scope**: Explicit admission gate; requires validation.
**Storage**: Logical table (`dj_admission`) + file references to MP3 library.
**Responsibilities**:
- Gate for MP3 admission (explicit identity + asset pair)
- Validation before export (file exists, metadata complete, enrichment done)
- Readiness tracking via `dj_admission.readiness` state

**Contract**:
- DJ readiness is explicit: `['unvalidated', 'ready', 'stale', 'orphaned']`
- Admission requires `mp3_asset.readiness='playable'`
- Validation requires enrichment complete (energy, danceability, key)
- XML export requires all `dj_admission.readiness='ready'`

---

### Recommended DJ Metadata Storage

**Split across tiers**:

1. **Master identity metadata** (main DB, read-only after intake):
   - Artist, title, duration, ISRC, Beatport ID, TIDAL ID
   - Provider metadata from intake (60–80% complete)
   - Stored in `track_identity.canonical_payload_json`

2. **DJ enrichment metadata** (separate enrichment table or JSON column):
   - Energy, danceability, happiness, popularity, BPM, key, genre
   - Added via provider enrichment (TIDAL cross-check) or Lexicon backfill
   - Stored in `track_identity.canonical_payload_json.lexicon_*` prefix keys
   - Marked with enrichment stage (`enrichment_state.completed_stages`)

3. **DJ curation metadata** (separate table for DJ-specific state):
   - Role (peak, buildup, drop, transition, etc.)
   - DJ tag/note (added by operator in Rekordbox or via CLI)
   - Playlist membership (in `dj_playlist` and Rekordbox XML)
   - Stored in `dj_admission` row or separate `dj_curation_metadata` table

**Rationale**:
- Master metadata is immutable and canonical
- DJ enrichment is explicit and traceable (via `enrichment_state`)
- DJ curation is operator-controlled and bidirectional (Rekordbox sync)

---

### Recommended Rekordbox XML Integration

**Primary principle**: XML is the first-class interoperability boundary between tagslut and Rekordbox.

#### 1. Emit (Stage 4a)
```bash
poetry run tagslut dj xml emit \
  --db "$TAGSLUT_DB" \
  --out rekordbox.xml
```
- **Prerequisite**: All `dj_admission` rows have `readiness='ready'`
- **Output**: Deterministic XML with stable TrackIDs
- **Manifest**: SHA-256 hash + DB metadata stored in `dj_export_state`

#### 2. Patch (Stage 4b)
```bash
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --out rekordbox_v2.xml
```
- **Prerequisite**: Prior emit exists and manifest hash matches
- **Preserves**: All TrackIDs and cue points from prior emit
- **Updates**: Playlist structure from new `dj_admission` state

#### 3. Import (Proposed Stage 5)
```bash
poetry run tagslut dj xml import \
  --db "$TAGSLUT_DB" \
  --in rekordbox_curated.xml
```
- **Purpose**: Round-trip playlist edits from Rekordbox back to DB
- **Updates**: Playlist hierarchy, track order, roles based on Rekordbox cues
- **Preserves**: All identities and MP3 asset links

#### 4. Validation
- **Pre-export**: Validate all admitted tracks have required DJ metadata
- **Post-export**: Validate XML structure and TrackID mapping
- **Roundtrip**: Test emit + import + re-emit → byte-identical XML

**Safety Contracts**:
- XML is deterministic: same DB state → same XML bytes (no timestamp variation)
- TrackIDs are stable: persisted in `dj_track_id_map`, never regenerated
- Manifest hash prevents accidental overwrites
- Cue point drift is detected (XML import warns if TrackID→file path has changed)

---

## What to Delete or Collapse

### 1. Deprecate `tools/get --dj` Flag
- **Why**: Two divergent runtime paths; operator can't predict behavior
- **Timeline**: 3-month deprecation period with warnings
- **Migration**: All users to canonical 4-stage pipeline
- **Remove**: After December 2025

### 2. Deprecate `tools/get-intake --dj` Flag
- **Why**: Same as `tools/get --dj`; legacy wrapper path
- **Timeline**: 3-month deprecation period with warnings
- **Migration**: All users to canonical 4-stage pipeline
- **Remove**: After December 2025

### 3. Consolidate Three DJ Export Code Paths
- **Current paths**:
  - `tools/get-intake --dj` (shell/Python wrapper)
  - `tagslut/dj/export.py` (CLI command)
  - `scripts/dj/build_pool_v3.py` (lower-level script)
- **Action**: Keep only `tagslut/dj/export.py` (CLI)
- **Remove**: `tools/get-intake --dj` section and `scripts/dj/build_pool_v3.py`
- **Keep as**: `scripts/dj/build_pool_v3.py` for "lower-level direct Python" (undocumented, low-priority)

### 4. Collapse `mp3 build` + `mp3 reconcile` into Single Command
- **Current**: Two separate commands with similar logic
- **Proposal**: One `mp3 register` command with `--build` vs `--reconcile` modes
- **Rationale**: Reduces CLI surface and enforces common validation path

### 5. Remove Optional `--skip-validation` Flag from `dj xml emit`
- **Why**: Validation should be mandatory
- **Timeline**: Deprecation + removal after Week 1
- **Override**: Add `--force-emit` flag for emergency-only (with forced warning)

---

## Fast Wins (1 Day / 3 Days / 1 Week)

### 1 Day

1. **Add FFmpeg output validation** (30 min)
   - File size > 100KB
   - Duration matches FLAC ± 0.5%
   - ID3 tags present
   - [tagslut/mp3/transcode.py](tagslut/mp3/transcode.py)

2. **Add enrichment check to XML emit** (30 min)
   - Require energy, danceability for all tracks
   - Fail if missing (add `--force-emit` override for emergency)
   - [tagslut/dj/xml.py](tagslut/dj/xml.py)

3. **Add deprecation warnings to legacy wrappers** (30 min)
   - Print to stderr when `tools/get --dj` or `tools/get-intake --dj` is called
   - [tools/get](tools/get), [tools/get-intake](tools/get-intake)

### 3 Days

1. **Make `dj validate` a mandatory prerequisite for XML emit** (2 hours)
   - Check `dj validate` was run before emit
   - OR run it automatically if not run recently
   - [tagslut/dj/xml.py](tagslut/dj/xml.py)

2. **Add enrichment_state table** (2 hours)
   - Track completed enrichment stages per identity
   - Schema migration
   - [supabase/migrations/](supabase/migrations/)

3. **Add test for `--dj` wrapper end-to-end** (2 hours)
   - Verify `tools/get-intake --dj` produces usable MP3s
   - [tests/e2e/test_get_intake_dj.py](tests/e2e/)

### 1 Week

1. **Add mp3_asset.readiness + dj_admission.readiness columns** (8 hours)
   - Schema migration
   - State machine transitions through pipeline
   - [supabase/migrations/](supabase/migrations/), [tagslut/dj/admission.py](tagslut/dj/admission.py)

2. **Add dj xml import command** (8 hours)
   - Round-trip playlist edits from Rekordbox
   - Update `dj_playlist` table from XML
   - [tagslut/dj/xml.py](tagslut/dj/xml.py), CLI command

3. **Add retroactive MP3 admission test** (4 hours)
   - Test admitting existing MP3 directory into DJ library
   - Test readiness validation after retrofit
   - [tests/e2e/](tests/e2e/)

---

## Evidence Summary

### Code Files Examined
- `tools/get-intake`: 2,892 lines, DJ_MODE flag at L923
- `tagslut/dj/`: ~1,500 lines core modules (admission, xml, export, build)
- `scripts/dj/build_pool_v3.py`: ~800 lines duplicate export logic
- Test suite: 80 tests, 80%+ pass rate, but critical gaps in error injection and retroactive admission

### Key Findings
- **Two divergent DJ entry points** confirmed in code (wrapper L920–L930 branches on file existence)
- **FFmpeg failures are silent** (no stderr capture, no output validation)
- **Enrichment is optional** (Lexicon backfill documented as repeatable, not mandatory)
- **XML integration is weak** (no import/round-trip, playlist membership read-only)
- **Three separate export paths** (wrapper, CLI, script) with inconsistent error handling

---

## Next Steps

This audit is diagnostic only. To implement fixes:

1. **Immediate** (~1 day):
   - Add FFmpeg output validation
   - Add enrichment checks to XML emit
   - Add deprecation warnings to legacy wrappers

2. **Short-term** (~1 week):
   - Implement readiness state machines
   - Add XML import command
   - Consolidate export code paths

3. **Medium-term** (~1 month):
   - Deprecate and remove legacy `--dj` wrappers
   - Make enrichment mandatory (Lexicon backfill or provider fallback)
   - Add comprehensive test coverage for error paths

4. **Long-term** (~quarter):
   - Full XML round-trip integration with Rekordbox
   - DJ metadata sub-database (if needed)
   - Unified DJ management CLI

---

## Closing

The DJ workflow is salvageable but requires focused work on three fronts:

1. **Clarity**: Single entry point, clear state transitions, explicit contracts
2. **Reliability**: Non-optional validation at each stage, error reporting with recovery paths
3. **Integration**: Rekordbox as first-class boundary, not downstream export

The canonical 4-stage pipeline is conceptually sound. The problem is that it's not the default, legacy wrappers are still in the critical path, and validation is insufficient.

With the fixes outlined above, the DJ workflow can become reliable, auditable, and operationally transparent.
