<!-- Status: Data model proposal. Schema recommendations. -->

# Data Model Recommendation

Proposal for restructuring DJ workflow data model to support clear master→MP3→DJ distinctions and reliable state tracking.

---

## Current State Assessment

### Schema Overview

**Core DJ tables**:
- `track_identity`: Master canonical recordings (ISRC-based)
- `asset_file`: File-to-identity mapping (FLAC + MP3 roles)
- `mp3_asset`: MP3 metadata and status tracking
- `dj_admission`: MP3 → DJ curated subset mapping
- `dj_track_id_map`: Rekordbox TrackID assignments (persistent across re-emits)
- `dj_export_state`: XML manifest metadata
- `dj_playlist`: Playlist hierarchy for Rekordbox

### Problems

1. **No explicit MP3 "readiness" state**
   - `mp3_asset.status` conflates confidence (does ISRC match?) with readiness (is file playable?)
   - Values: `['suspected', 'verified', 'quarantine']`
   - Admission logic checks `status='verified'` but doesn't validate file or metadata
   - No way to distinguish "I'm not sure this is the right track" from "This file is corrupted"

2. **No DJ "readiness" state**
   - Admission table has no status or readiness marker
   - `dj_validate` outputs report but doesn't update admission state
   - XML emit doesn't run pre-flight checks or update state
   - Operator doesn't know if DJ library is ready for export without running validate separately

3. **No enrichment status tracking**
   - No table records which enrichment stages have been completed
   - Operator can't tell if track has required DJ fields (energy, danceability, key)
   - Lexicon backfill is optional and manual; no tracking if it's been run

4. **Complex JOIN chain**
   - To trace one track: `track_identity` → `asset_file` (x2 roles) → `mp3_asset` → `dj_admission` → `dj_track_id_map`
   - ~6 JOINs for a simple query

5. **No explicit cascade semantics**
   - Deleting a FLAC doesn't cascade to mp3_asset or dj_admission
   - Orphaned rows can accumulate without notice

---

## Recommended Schema Changes

### 1. Add `mp3_asset.readiness` Column

**Purpose**: Distinguish metadata confidence from file playability.

**Definition**:
```sql
ALTER TABLE mp3_asset ADD COLUMN readiness TEXT DEFAULT 'unchecked'
  CONSTRAINT mp3_asset_readiness_values CHECK (readiness IN (
    'unchecked',        -- Initial state; no validation run
    'playable',         -- Output validation passed: size, duration, ID3 OK
    'suspect',          -- File exists but validation failed (size too small, corrupted ID3, etc.)
    'corrupted',        -- Deliberate corruption detected (e.g., empty file, wrong codec)
    'orphaned'          -- FLAC master used for transcode has been deleted from master library
  ))
```

**State Transitions**:
- `unchecked` → `playable`: After `mp3 build` validates output successfully
- `unchecked` → `suspect`: After reconcile discovers file with incomplete metadata or ID3 issues
- `suspect` → `playable`: After operator reviews and approves in reconcile_log, then re-validates
- `playable` → `orphaned`: If linked FLAC is deleted from master library
- Any → `corrupted`: If file becomes unreadable

**Affected Workflows**:
- `mp3 build`: After output validation, set `readiness='playable'`
- `mp3 reconcile`: Set `readiness='suspect'` for low-confidence matches; `readiness='playable'` for high-confidence
- `dj_backfill`: Only admit rows where `readiness IN ('playable', 'orphaned')`
- `dj_validate`: Update `readiness='orphaned'` if linked FLAC deleted

---

### 2. Add `dj_admission.readiness` Column

**Purpose**: Track DJ-layer validation state; make it explicit before export.

**Definition**:
```sql
ALTER TABLE dj_admission ADD COLUMN readiness TEXT DEFAULT 'unvalidated'
  CONSTRAINT dj_admission_readiness_values CHECK (readiness IN (
    'unvalidated',      -- Admitted but not yet validated
    'ready',            -- dj_validate() has passed for this track
    'stale',            -- Was ready, but state changed (MP3 deleted, identity enrichment changed)
    'orphaned',         -- MP3 or identity no longer accessible
    'blocked'           -- Operator has flagged this track (e.g., copyright issue)
  ))
```

**State Transitions**:
- `unvalidated` → `ready`: After `dj validate` passes all checks
- `ready` → `stale`: If MP3 file deleted or identity enrichment changes post-validation
- `ready` → `orphaned`: If linked mp3_asset or identity is deleted
- `ready` → `blocked`: If operator blocks the track (manual override)
- `unvalidated` / `stale` / `orphaned` → `ready`: After re-running `dj validate` and it passes

**Affected Workflows**:
- `dj_admit` / `dj_backfill`: Set `readiness='unvalidated'` (initial state)
- `dj_validate`: Set `readiness='ready'` for tracks that pass all checks
- `dj_xml_emit`: Require all `dj_admission.readiness='ready'` OR `--force-emit` flag

---

### 3. Add `enrichment_state` Table

**Purpose**: Track which enrichment stages have been completed per track_identity.

**Definition**:
```sql
CREATE TABLE enrichment_state (
  identity_id INTEGER PRIMARY KEY,
  intake_complete_at TIMESTAMP,
  provider_metadata_complete_at TIMESTAMP,
  lexicon_backfill_complete_at TIMESTAMP,
  beatport_enrichment_complete_at TIMESTAMP,
  tidal_enrichment_complete_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  -- Tracking which fields are present
  has_energy BOOLEAN,
  has_danceability BOOLEAN,
  has_bpm BOOLEAN,
  has_key BOOLEAN,
  has_popularity BOOLEAN,

  FOREIGN KEY (identity_id) REFERENCES track_identity(id) ON DELETE CASCADE
)
```

**State Management**:
- `intake_complete_at`: Set when track_identity is created
- `provider_metadata_complete_at`: Set after provider enrichment (Beatport/TIDAL)
- `lexicon_backfill_complete_at`: Set after Lexicon backfill runs
- Boolean fields updated whenever enrichment runs

**Affected Workflows**:
- `intake`: Set `intake_complete_at` and `provider_metadata_complete_at`
- `lexicon_backfill`: Set `lexicon_backfill_complete_at` and update boolean fields
- `dj_xml_emit`: Check `has_energy`, `has_danceability`, `has_key` before emit (unless `--force-emit`)

---

### 4. Add `mp3_asset.validation_details_json` Column

**Purpose**: Store detailed validation output for auditing and debugging.

**Definition**:
```sql
ALTER TABLE mp3_asset ADD COLUMN validation_details_json TEXT DEFAULT '{}';
```

**Content**:
```json
{
  "output_file_size_kb": 2048,
  "expected_duration_sec": 223,
  "actual_duration_sec": 224,
  "id3_tag_valid": true,
  "id3_artist": "Artist Name",
  "id3_title": "Track Title",
  "id3_album": "Album Name",
  "ffmpeg_exit_code": 0,
  "ffmpeg_stderr": "",
  "validation_timestamp": "2026-03-22T15:30:00Z"
}
```

**Used by**:
- `mp3 build`: Store validation result after transcoding
- `mp3 reconcile`: Store ID3 extraction details
- Operator debugging: Query mp3_asset to see why a file was marked suspect

---

### 5. Rename and Clarify Table Purposes

**Current**:
- `files.dj_flag` (legacy, removed)
- `dj_admission` (DJ curation layer)

**Proposed clarification**:
- Keep `dj_admission` but add explicit readiness contract
- Add comments to schema documenting three-layer model:
  - **Master layer** (`asset_file` with `role='master'`): FLAC canonical sources
  - **MP3 layer** (`mp3_asset`, `asset_file` with `role='mp3'`): Derived MP3 copies
  - **DJ layer** (`dj_admission`, `dj_playlist`): Curated DJ-specific subset

---

## Data Flow with New Schema

### Master FLAC Library

**Schema**:
```
track_identity (ISRC-based identity)
  ↓
  asset_file (role='master')
  ↓
  File on disk: $MASTER_LIBRARY/...

enrichment_state
  ↓
  canonical_payload_json (provider metadata + lexicon enrichment)
```

**State Contract**:
- Once created, track_identity is immutable (except enrichment_state updates)
- Asset file is read-only after intake
- Enrichment is optional but trackable

---

### MP3 Library

**Schema**:
```
mp3_asset (from build or reconcile)
  ├─ readiness ('unchecked' → 'playable' → 'orphaned' / 'corrupted')
  ├─ validation_details_json (build output info)
  ├─ asset_file (role='mp3')
  └─ File on disk: $DJ_LIBRARY/...

  └─ linked to track_identity via asset_file
  └─ linked to enrichment_state (for DJ metadata)
```

**State Contract**:
- Only tracks with `readiness='playable'` can be admitted to DJ library
- File validation is mandatory before admission
- Readiness is explicitly tracked and queryable

---

### DJ Library

**Schema**:
```
dj_admission (identity + mp3_asset)
  ├─ readiness ('unvalidated' → 'ready' → 'stale' / 'orphaned' / 'blocked')
  ├─ identity_id → track_identity (enrichment_state)
  ├─ mp3_asset_id → mp3_asset (readiness='playable')
  └─ linked to dj_track_id_map (Rekordbox TrackID)
  └─ linked to dj_playlist (Rekordbox hierarchy)
```

**State Contract**:
- All admitted tracks must have `readiness='ready'` before XML export
- Validation is mandatory and state-based
- Failed validation prevents export (unless --force-emit override)

---

## Backward Compatibility

### Query Equivalence

**Old query** (check if MP3 is safe to admit):
```sql
SELECT * FROM mp3_asset WHERE status='verified'
```

**New query**:
```sql
SELECT * FROM mp3_asset WHERE readiness='playable'
```

**Migration**:
- Run one-time migration: `UPDATE mp3_asset SET readiness='playable' WHERE status='verified'`
- Run one-time migration: `UPDATE mp3_asset SET readiness='suspect' WHERE status='suspect'`
- Update application code to query `readiness` instead of `status`

### Backfill Existing Data

**For existing mp3_asset rows**:
```sql
-- If status='verified' and file still exists, mark as playable
UPDATE mp3_asset SET readiness='playable'
WHERE status='verified'
AND EXISTS (SELECT 1 FROM asset_file WHERE id=mp3_asset.asset_file_id)
AND filesystem_check(file_path) = 'exists';

-- If status='suspect', keep as suspect (no validation done)
UPDATE mp3_asset SET readiness='suspect' WHERE status='suspect';
```

**For existing dj_admission rows**:
```sql
-- If MP3 is playable and was admitted, assume it was validated
UPDATE dj_admission SET readiness='ready'
WHERE mp3_asset_id IN (SELECT id FROM mp3_asset WHERE readiness='playable');

-- Otherwise mark as unvalidated (requires re-validate)
UPDATE dj_admission SET readiness='unvalidated'
WHERE readiness IS NULL;
```

**For enrichment_state**:
```sql
-- Create entries for all existing track_identity rows
INSERT IGNORE INTO enrichment_state (identity_id, intake_complete_at, provider_metadata_complete_at)
SELECT id, created_at, created_at FROM track_identity;

-- Set enrichment flags based on canonical_payload_json content
UPDATE enrichment_state SET has_energy=1
WHERE identity_id IN (SELECT id FROM track_identity WHERE json_extract(canonical_payload_json, '$.energy') IS NOT NULL);
-- ...repeat for other fields
```

---

## Migration Path

### Phase 1: Add Columns (Non-Breaking)
1. Add `mp3_asset.readiness` with default='unchecked'
2. Add `dj_admission.readiness` with default='unvalidated'
3. Add `mp3_asset.validation_details_json` with default='{}'
4. Create `enrichment_state` table
5. Backfill existing data (see above)
6. Deploy without changing application logic (old queries still work)

### Phase 2: Update Application Logic
1. Update `mp3 build` to set `readiness='playable'` after validation
2. Update `mp3 reconcile` to set `readiness` based on confidence
3. Update `dj_backfill` to require `readiness='playable'`
4. Update `dj_validate` to set `readiness='ready'`
5. Update `dj_xml_emit` to require `readiness='ready'` (fail without --force-emit)

### Phase 3: Update Tests
1. Add tests for readiness state transitions
2. Add tests for preflight validation before XML emit
3. Add tests for stale state detection

### Phase 4: Deprecate Old Fields (Optional)
1. Once all code uses readiness, `status` column becomes redundant
2. Consider keeping for audit trail, or drop after 6-month deprecation

---

## Benefits

| Aspect | Current | With New Model |
|--------|---------|-----------------|
| State clarity | Implicit (must infer from table presence) | Explicit (readiness column) |
| Validation enforcement | Optional (operator choice) | Mandatory (state machine) |
| Enrichment tracking | Not tracked | Explicit (enrichment_state) |
| Operator visibility | Low (must run cli.dj validate report) | High (query readiness columns) |
| Error detection | Post-hoc (during export) | Pre-emptive (at each stage) |
| Auditability | Limited (logs only) | Complete (state transitions + details_json) |
| Recovery | Manual DB editing | Clear state path to "ready" |

---

## Risk Assessment

### Migration Risk: **LOW**
- Columns are ENUMs with safe defaults
- Old queries continue to work (new columns don't break existing queries)
- Backfill is idempotent and can be verified

### Query Performance: **NO IMPACT**
- New columns are indexed by default (readiness, enrichment_state)
- JOIN count doesn't increase

### Operator Learning Curve: **MEDIUM**
- Need to understand three-level readiness states
- Documentation and CLI feedback must be clear

---

## Implementation Priority

**Week 1**: Schema migration (columns + backfill)
**Week 2**: Application logic update (state transitions)
**Week 3**: Test coverage + documentation

---

## Conclusion

The new data model makes DJ workflow state explicit, auditable, and operator-visible. It enables:
1. **Validation-first design**: Pre-conditions are checked before operations, not after
2. **State-machine clarity**: Each layer (master → MP3 → DJ) has explicit readiness state
3. **Error prevention**: Problems are caught early with clear recovery paths
4. **Operator transparency**: CLI output shows current state, not just operations performed

This foundation enables reliable DJ workflows and makes it safe to remove manual workarounds and emergency overrides.
