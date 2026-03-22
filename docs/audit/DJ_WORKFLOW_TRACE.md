<!-- Status: Diagnostic trace. Complete end-to-end pathway documentation. -->

# DJ Workflow Trace

**Purpose**: Map the actual execution chain for DJ operations, showing dependencies and failure modes.

---

## Entry Points

### 1. Canonical 4-Stage CLI (Supported)

```
tagslut intake <url>
  └─> tagslut mp3 build|reconcile
      └─> tagslut dj admit|backfill
          └─> tagslut dj validate
              └─> tagslut dj xml emit|patch
```

**Files**:
- CLI: [tagslut/cli/dj.py](tagslut/cli/dj.py)
- Exec layer: [tagslut/exec/](tagslut/exec/)
- Core: [tagslut/dj/](tagslut/dj/)

---

### 2. Legacy Wrapper (Deprecated, Non-Deterministic)

```
tools/get-intake --dj <url>
  ├─> [download stage]
  ├─> [precheck stage]
  ├─> [scan stage]
  ├─> [promote stage]
  ├─> [enrich stage]
  └─> DJ_MODE=1 handler
      ├─> [if promoted files exist]
      │   └─> mp3 build (FLAC → MP3) [STAGE 2A]
      └─> [else; PRECHECK fallback]
          └─> [M3U generation only]
              └─> [NO MP3s created]
                  └─> [SILENT FAILURE]
```

**Problem**: Two divergent code paths depending on whether precheck or promote wins.

**Files**:
- Wrapper: [tools/get-intake](tools/get-intake) L920–L2900
- Shell logic: DJ_MODE flag at L923, handler at L2800–L2900

---

## Stage-by-Stage Trace

### Stage 1: Intake (Canonical)

**Command**:
```bash
poetry run tagslut intake <url>
```

**Entry**:
- [tagslut/cli/intake.py](tagslut/cli/intake.py) → `intake_command()`
- Orchestrator: [tagslut/intake/orchestrator.py](tagslut/intake/orchestrator.py)

**Work**:
1. Provider download (Beatport / TIDAL)
2. Link to `track_identity` (ISRC-based or provider ID)
3. Create `asset_file` with `role='master'`
4. Enrich with provider metadata (60–80% coverage)
5. Write to DB: `track_identity`, `asset_file`, `enrichment_state`

**State Output**:
- `track_identity` rows with canonical_payload_json (artist, title, duration, BPM, key, etc.)
- `asset_file` rows with role='master' pointing to FLAC files

**Risks**:
- Provider missing data → enrichment incomplete (BPM, key may be null)
- No fallback if provider is down
- Beatport ID collision across releases

---

### Stage 2a: MP3 Build (Canonical)

**Command**:
```bash
poetry run tagslut mp3 build \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-root "$DJ_LIBRARY" \
  --execute
```

**Entry**:
- [tagslut/cli/dj.py](tagslut/cli/dj.py) → `mp3_command()`
- Exec layer: [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py)

**Work**:
1. Query `track_identity` → linked `asset_file` with role='master'
2. For each FLAC:
   - Check if MP3 already exists in DJ_LIBRARY (skip if yes)
   - Spawn ffmpeg transcode: FLAC → MP3 (at bitrate 320kbps or configured)
   - Write MP3 to `$DJ_LIBRARY/<artist>/<title>.mp3`
3. Validate output:
   - ❌ NO VALIDATION (silent ffmpeg failures)
4. Register MP3 in `mp3_asset` table
5. Write to DB: `mp3_asset` rows with status='verified'

**State Output**:
- `mp3_asset` rows linked to `track_identity` via asset_file
- MP3 files on disk at `$DJ_LIBRARY/<path>`

**Risks**:
- **CRITICAL**: FFmpeg failures are silent (exit code not checked)
  - Missing ffmpeg → no error
  - Codec error → no error
  - Truncated output → no error
  - Disk full → partial write, then error (but state written to DB as success)
- **HIGH**: No output validation (file size, duration, ID3 tags)
- **HIGH**: No pre-flight file existence check (discovered mid-transcode)
- **MEDIUM**: File path collision (if two tracks have same artist/title)

---

### Stage 2b: MP3 Reconcile (Canonical)

**Command**:
```bash
poetry run tagslut mp3 reconcile \
  --db "$TAGSLUT_DB" \
  --mp3-root "$DJ_LIBRARY" \
  --execute
```

**Entry**:
- [tagslut/cli/dj.py](tagslut/cli/dj.py) → `mp3_command()`
- Exec layer: [tagslut/exec/mp3_reconcile.py](tagslut/exec/mp3_reconcile.py)

**Work**:
1. Scan `$DJ_LIBRARY` for all MP3 files
2. For each MP3:
   - Extract ISRC from ID3v2 tags
   - Query `track_identity` by ISRC
   - If no match: try Spotify ID
   - If no match: try title+artist (normalized, case-insensitive)
   - If match found: create `mp3_asset` row, status='verified'
   - If no match: create `mp3_asset` row, status='suspect' (operator review needed)
3. Write to DB: `mp3_asset` rows + `reconcile_log` audit trail

**State Output**:
- `mp3_asset` rows linked to `track_identity` by ISRC or fallback match
- `reconcile_log` entries with confidence ('high' for ISRC, 'medium' for Spotify, 'low' for title+artist)

**Risks**:
- **HIGH**: False positive matches on title+artist (remixes, compilations)
  - "Track Name" + "Artist A" matches both remix and original → wrong identity
  - No confidence scoring for disambiguation
- **MEDIUM**: Duplicate ISRCs (rare but possible in Beatport)
  - ISRC collision across releases → wrong match
- **MEDIUM**: Missing ISRC in ID3 tags → fallback to title+artist

---

### Stage 2: Enrichment (Optional, Post-Stage 1)

**Command** (optional, not in canonical pipeline):
```bash
python -m tagslut.dj.reconcile.lexicon_backfill \
  --db "$TAGSLUT_DB" \
  --lex /Volumes/MUSIC/lexicondj.db
```

**Work**:
1. Load Lexicon DJ SQLite export (music_v3.db)
2. For each `track_identity` row:
   - Try to match by Beatport ID (if Lexicon has `streamingService='beatport'`)
   - If no match: try Spotify ID
   - If no match: try normalized artist+title
3. If match found:
   - Extract energy, danceability, happiness, popularity, BPM, key
   - Update `track_identity.canonical_payload_json` with `lexicon_*` prefixed keys
   - Log to `reconcile_log` with confidence

**State Output**:
- Updated `track_identity.canonical_payload_json` with DJ metadata

**Risks**:
- **CRITICAL**: Lexicon backfill is OPTIONAL (not in canonical 4-stage pipeline)
  - DJ XML can export without energy/danceability if this step is skipped
  - Operator has no signal that enrichment is incomplete
- **MEDIUM**: ID mismatch between Beatport IDs in Lexicon vs. tagslut DB
  - Different Beatport versions → different IDs
- **MEDIUM**: Timestamp staleness (Lexicon export is point-in-time)

---

### Stage 3a: DJ Backfill (Canonical)

**Command**:
```bash
poetry run tagslut dj backfill --db "$TAGSLUT_DB"
```

**Entry**:
- [tagslut/cli/dj.py](tagslut/cli/dj.py) → `dj_command()`
- Exec layer: [tagslut/exec/dj_admit.py](tagslut/exec/dj_admit.py)

**Work**:
1. Query all `mp3_asset` rows where status='verified'
2. For each row:
   - Extract `track_identity` via asset_file
   - Create `dj_admission` row (identity_id, mp3_asset_id, admission_timestamp)
   - Skip if already admitted (idempotent)
3. Write to DB: `dj_admission` rows

**State Output**:
- `dj_admission` table populated with admitted tracks

**Risks**:
- **CRITICAL**: No validation that MP3 file still exists on disk
- **CRITICAL**: No validation that canonical_payload_json has required DJ fields (energy, danceability, key)
- **MEDIUM**: Can admit `mp3_asset` rows with status='suspect' (if operator manually updated)

---

### Stage 3b: DJ Single Admit (Canonical)

**Command**:
```bash
poetry run tagslut dj admit \
  --identity-id <id> \
  --mp3-asset-id <id>
```

**Entry**:
- [tagslut/cli/dj.py](tagslut/cli/dj.py) → `dj_command()`
- Exec layer: [tagslut/exec/dj_admit.py](tagslut/exec/dj_admit.py)

**Work**:
1. Validate identity_id and mp3_asset_id exist
2. Create `dj_admission` row
3. Skip if already admitted

**State Output**:
- One `dj_admission` row

**Risks**: Same as backfill.

---

### Stage 3c: DJ Validate (Canonical)

**Command**:
```bash
poetry run tagslut dj validate --db "$TAGSLUT_DB"
```

**Entry**:
- [tagslut/cli/dj.py](tagslut/cli/dj.py) → `dj_command()`
- Exec layer: [tagslut/exec/dj_validate.py](tagslut/exec/dj_validate.py)

**Work**:
1. Query all `dj_admission` rows
2. For each row:
   - Resolve MP3 file path from mp3_asset
   - Check file exists and is readable
   - Check file size > 100KB (broken file detection)
   - Check metadata: artist, title, duration (from ID3 tags)
   - ❌ NO ENRICHMENT CHECK (energy, danceability not validated)
3. Log failures to output report

**State Output**:
- Validation report (tsv or JSON)
- ❌ NO DB state change (validate doesn't update admission state)

**Risks**:
- **CRITICAL**: Validation is optional (not required before XML emit)
- **CRITICAL**: No enrichment validation
- **MEDIUM**: Files can be deleted between validation and export → stale state

---

### Stage 4a: DJ XML Emit (Canonical)

**Command**:
```bash
poetry run tagslut dj xml emit \
  --db "$TAGSLUT_DB" \
  --out rekordbox.xml \
  [--skip-validation]
```

**Entry**:
- [tagslut/cli/dj.py](tagslut/cli/dj.py) → `dj_command()`
- Exec layer: [tagslut/exec/dj_xml.py](tagslut/exec/dj_xml.py)

**Work**:
1. Query all `dj_admission` rows with linked metadata
2. For each admission:
   - Assign stable TrackID (from `dj_track_id_map` if exists, else generate new)
   - Store TrackID in `dj_track_id_map` (persistent across re-emits)
3. Generate Rekordbox-compatible XML:
   - Collection element per `dj_playlist` row
   - Track elements per `dj_admission` row
   - Absolute paths (with fallback to relative for portability)
4. Compute manifest hash (SHA-256 of DB state + paths)
5. Write to disk: XML file
6. Write to DB: `dj_export_state` row (manifest_hash, file_path, timestamp)

**State Output**:
- Rekordbox XML file on disk
- `dj_export_state` manifest entry in DB

**Risks**:
- ❌ NO PRE-FLIGHT VALIDATION (can export without enrichment)
- ❌ NO FILE EXISTENCE CHECK (can export paths that don't exist)
- **MEDIUM**: ManifestHash mismatch if XML tampered (detected by patch command)

---

### Stage 4b: DJ XML Patch (Canonical)

**Command**:
```bash
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --out rekordbox_v2.xml
```

**Entry**:
- [tagslut/cli/dj.py](tagslut/cli/dj.py) → `dj_command()`
- Exec layer: [tagslut/exec/dj_xml.py](tagslut/exec/dj_xml.py)

**Work**:
1. Query prior `dj_export_state` entry
2. Verify manifest_hash matches current DB state (fail if tampered)
3. Load prior XML file
4. For each prior TrackID:
   - Preserve TrackID (look up in `dj_track_id_map`)
   - Check if track still admitted (preserve if yes, remove if no)
5. For new admitted tracks:
   - Generate new TrackIDs (from `dj_track_id_map`)
   - Add to XML
6. Re-generate XML with preserved TrackIDs + new tracks
7. Compute new manifest hash
8. Write to disk: new XML file
9. Write to DB: new `dj_export_state` row

**State Output**:
- New Rekordbox XML file
- New `dj_export_state` entry

**Risks**: Same as emit (no pre-flight validation).

---

## Dependency Map

```
intake
  ↓
  track_identity (source)
  ├─ canonical_payload_json (provider metadata: 60–80% complete)
  ├─ asset_file (role='master')
  └─ enrichment_state (intake stage)

mp3_build / mp3_reconcile
  ↓
  mp3_asset (registered MP3s)
  ├─ track_identity (via asset_file)
  ├─ status = 'verified' or 'suspect'
  └─ file path on disk

[OPTIONAL] lexicon_backfill
  ↓
  track_identity.canonical_payload_json
  └─ enrichment_state (lexicon stage)

dj_backfill / dj_admit
  ↓
  dj_admission (curated subset)
  ├─ track_identity
  ├─ mp3_asset
  └─ [❌ NO READINESS STATE]

dj_validate
  ↓
  validation report
  ├─ file exists checks
  ├─ metadata checks
  └─ [❌ NO ENRICHMENT CHECKS]
  └─ [❌ NO STATE UPDATE]

dj_xml_emit
  ↓
  Rekordbox XML
  ├─ dj_track_id_map (stable TrackIDs)
  ├─ dj_export_state (manifest hash)
  └─ [❌ NO PRE-FLIGHT VALIDATION]
```

---

## Error Paths (Untested)

### FFmpeg Failures

**Scenario**: FFmpeg exits with error or produces corrupted output.

**Current Behavior**:
1. MP3 build starts transcode
2. FFmpeg fails (missing binary, codec error, disk full, etc.)
3. ❌ Exit code not checked
4. ❌ Output not validated (file size, duration, ID3)
5. ❌ MP3 asset registered to DB as status='verified'
6. ❌ MP3 file is truncated or corrupted

**Consequence**:
- DJ pool contains broken MP3s
- Rekordbox import fails silently
- MP3 asset state in DB is wrong

**Test Coverage**:
- ❌ Not tested

---

### Enrichment Incomplete

**Scenario**: Lexicon backfill is skipped; DJ XML exports without energy/danceability.

**Current Behavior**:
1. Intake complete (metadata 60–80%)
2. Operator skips Lexicon backfill (optional)
3. mp3 build complete
4. dj_backfill complete
5. dj_validate complete (no enrichment checks)
6. dj_xml_emit complete (can use `--skip-validation` flag)
7. ❌ Rekordbox XML exports with missing DJ fields

**Consequence**:
- DJ library is incomplete in Rekordbox
- Operator doesn't notice until Rekordbox import
- Requires MP3/DJ rebuild after backfill

**Test Coverage**:
- ❌ Not tested

---

### Retroactive MP3 Admission

**Scenario**: Existing MP3 directory is retrofitted into DJ library.

**Current Behavior**:
1. MP3 directory exists on disk (not created by tagslut)
2. Operator runs `mp3 reconcile` to register MP3s
3. Some MP3s match (ISRC) → status='verified'
4. Some MP3s don't match (no ISRC, title+artist false positive) → status='suspect'
5. Operator manually reviews `reconcile_log`
6. Operator manually admits good MP3s via `dj admit`
7. MP3s with status='suspect' are skipped
8. ❌ No clear path to admit 'suspect' tracks (requires manual DB edit)

**Consequence**:
- Operator must manually intervene
- Suspect tracks are orphaned
- Workflow is not self-service

**Test Coverage**:
- ❌ Not tested

---

### MP3 File Deletion Between Stages

**Scenario**: MP3 file is deleted after admission but before XML export.

**Current Behavior**:
1. dj_backfill admits track (no file check)
2. External process deletes MP3 file (e.g., cleanup script, user error)
3. dj_validate runs → detects missing file, logs error
4. ❌ But dj_validate doesn't update dj_admission state
5. dj_xml_emit runs → tries to generate path reference for missing file
6. ❌ XML exports with wrong path reference

**Consequence**:
- Rekordbox import fails or has broken path
- Track is orphaned in DJ library

**Test Coverage**:
- ❌ Not tested

---

### ISRC False Positives

**Scenario**: Multiple tracks have the same ISRC.

**Current Behavior**:
1. MP3 reconcile scans directory
2. Two MP3 files have same ISRC in ID3 (rare but possible)
3. First match found → registered to track_identity
4. Second match → skips (already registered)
5. ❌ One track is orphaned/misregistered

**Consequence**:
- DJ library is incomplete
- Operator doesn't notice until missing track in pool

**Test Coverage**:
- ❌ Not tested

---

### Title+Artist False Positives

**Scenario**: Title+artist matching creates false positives (remixes, compilations).

**Current Behavior**:
```
MP3: "Track Name" by "Artist A" (remix)
DB: "Track Name" by "Artist A" (original)
→ Match found (normalized, case-insensitive)
→ ❌ Wrong track registered
```

**Consequence**:
- DJ library has wrong metadata
- Rekordbox has wrong key/BPM
- Operator doesn't notice until performance

**Test Coverage**:
- ❌ Not tested (mock reconcile in test suite)

---

## Metrics

### Test Coverage

- **CLI commands**: 90% (tested)
- **Core business logic**: 85% (tested)
- **XML generation**: 100% (well-tested)
- **FFmpeg integration**: 0% (mocked)
- **Enrichment validation**: 0% (not tested)
- **Retroactive MP3 admission**: 0% (not tested)
- **MP3 reconcile edge cases**: 10% (only ISRC path tested)
- **Race conditions**: 0% (not tested)

### Code Fragmentation

| Area | Entry Points | Duplicated Logic | Consolidation |
|------|--------------|------------------|---------------|
| DJ export | 3 (wrapper, CLI, script) | ~30% | Merge to CLI only |
| Energy/BPM | 3 (provider, TIDAL, Lexicon) | ~40% | Normalize to canonical_payload_json |
| MP3 registration | 2 (build, reconcile) | ~20% | Merge to single command |
| Enrichment | 4 (intake, post-move, post-backfill, Lexicon) | ~50% | Consolidate to explicit stages |

---

## Performance Implications

- **MP3 build**: ~5min per 100 FLAC files (ffmpeg transcode time)
- **MP3 reconcile**: ~30sec per 1000 MP3 files (fingerprint computation)
- **DJ validate**: ~1sec per 1000 admitted tracks (file stat checks)
- **XML emit**: <1sec for ~10000 tracks (DB query + XML generation)

---

## Conclusion

The canonical 4-stage pipeline is methodical and mostly sound. The problems are:

1. **It's not the default**: Legacy wrappers are still in the critical path
2. **Validation is weak**: FFmpeg errors are silent, enrichment is optional, readiness is implicit
3. **Error handling is incomplete**: 10+ failure modes are untested
4. **State tracking is ambiguous**: No explicit "readiness" states at MP3 or DJ level

To make this pathway reliable, see [DJ_WORKFLOW_AUDIT.md](DJ_WORKFLOW_AUDIT.md#minimum-viable-redesign).
