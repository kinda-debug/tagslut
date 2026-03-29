<!-- Status: Integration architecture. Rekordbox as primary interop boundary. -->

# Rekordbox XML Integration

Recommended architecture for seamless Rekordbox integration as first-class interoperability boundary.

---

## Current State Assessment

### Strengths

✓ **Deterministic generation**: Same DB state → same XML bytes (testable)
✓ **Stable TrackID assignment**: Via dj_track_id_map (persisted across re-emits)
✓ **Manifest hash validation**: Prevents accidental overwrites and tampering detection
✓ **Emit/patch cycle works**: Can update XML without resetting Rekordbox cue points

### Weaknesses

✗ **XML is optional**: Not required for DJ library to be "complete"
✗ **One-way export**: No import command to round-trip playlist edits from Rekordbox
✗ **Playlist hierarchy read-only**: Changes in Rekordbox don't sync back to DB
✗ **Cue points not ingested**: Rekordbox cue data (beat grid, hot cues) ignored on re-import
✗ **No conflict resolution**: Unclear what happens if Rekordbox and DB state diverge
✗ **XML paths can break**: Files moved on disk → XML references become stale

---

## Recommended Architecture

### Principle: XML as Bidirectional Boundary

XML is not merely an export artifact. It's the canonical serialization format for DJ-Rekordbox integration. All Rekordbox-facing operations pass through XML projection with explicit round-trip safety.

---

## Stage 4a: XML Emit (Deterministic Export)

**Command**:
```bash
poetry run tagslut dj xml emit \
  --db "$TAGSLUT_DB" \
  --out rekordbox.xml \
  [--profile default|extended] \
  [--path-mode absolute|relative|mixed]
```

**Prerequisite**:
- All `dj_admission` rows have `readiness='ready'`
- All linked MP3 files exist and are readable
- All required DJ metadata (energy, danceability, key) present

**Behavior**:
1. Query all `dj_admission` rows with linked metadata
2. For each admission:
   - Assign stable TrackID (from `dj_track_id_map` if exists, else generate)
   - Store TrackID → (identity_id, mp3_asset_id) in `dj_track_id_map`
3. Generate Rekordbox-compatible XML:
   - Collection element per `dj_playlist` row (hierarchy)
   - Track elements per `dj_admission` row
   - Paths: absolute (default), relative (portable), or mixed
   - Metadata: artist, title, BPM, key, energy, etc.
4. Compute manifest hash: SHA-256(`dj_admission` IDs + paths + metadata snapshot)
5. Write XML to disk
6. Write `dj_export_state` entry:
   - manifest_hash
   - file_path
   - profile (default/extended)
   - path_mode (absolute/relative/mixed)
   - timestamp (emit time)
   - source ('emit' vs. 'patch')

**Output**:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="rekordbox" Version="6.0.0" Company="Pioneer"/>
  <COLLECTION Entries="123">
    <!-- All admitted MP3 tracks with stable TrackIDs -->
    <TRACK TrackID="12345" Name="..." Artist="..."...>
      <LOCATION Type="Local" RelativePath="..."/>
      <INFO BitRate="320" .../>
      <TEMPO BPM="128.5"/>
      <MUSICAL_KEY Type="9A"/>  <!-- Camelot notation -->
      <TAGS Energy="8" Danceability="7"/>
    </TRACK>
    ...
  </COLLECTION>
  <PLAYLISTS>
    <PLAYLIST Name="..." Entries="...">
      <PLAYLIST_TRACK TrackID="12345"/>
      ...
    </PLAYLIST>
  </PLAYLISTS>
</DJ_PLAYLISTS>
```

---

## Stage 4b: XML Patch (Incremental Update)

**Command**:
```bash
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --out rekordbox_v2.xml \
  [--source rekordbox_v1.xml] \
  [--keep-cues]
```

**Prerequisite**:
- Prior `dj_export_state` entry exists (manifest history)
- Manifest hash of prior XML matches current DB state (tampering check)
- All new/updated `dj_admission` rows have `readiness='ready'`

**Behavior**:
1. Load prior `dj_export_state` entry
2. Verify manifest_hash matches prior XML file
3. Load prior XML file from disk
4. For each `dj_track_id_map` entry:
   - If still admitted: preserve TrackID, preserve cue points
   - If no longer admitted: remove track element
5. For each new `dj_admission` row:
   - Assign new TrackID (generate if not in `dj_track_id_map`)
   - Add track element to collection
6. For each updated admission (metadata changed):
   - Preserve TrackID
   - Update metadata fields (BPM, key, energy, etc.)
   - Preserve cue points (if `--keep-cues`)
7. Update playlist membership based on new `dj_playlist` state
8. Re-generate XML with merged state
9. Compute new manifest_hash
10. Write XML to disk
11. Write new `dj_export_state` entry

**Output**: Updated XML with:
- Preserved TrackIDs (cue points survive)
- New track additions
- Removed track deletions
- Updated metadata

---

## Stage 4c: XML Import (Proposed, Future)

**Purpose**: Round-trip playlist edits from Rekordbox back to DB.

**Command**:
```bash
poetry run tagslut dj xml import \
  --db "$TAGSLUT_DB" \
  --in rekordbox_curated.xml [modified in Rekordbox] \
  [--merge-playlists] \
  [--resolve conflicts: ours|theirs|prompt]
```

**Prerequisite**:
- XML from a prior `dj xml emit` or `dj xml patch`
- File matches an entry in `dj_export_state` (or close enough for merge)

**Behavior**:
1. Parse XML into track + playlist data
2. For each track:
   - Look up TrackID in `dj_track_id_map`
   - Resolve to (identity_id, mp3_asset_id)
   - Extract metadata from XML (BPM, key, energy, cues)
3. Compare XML playlist structure vs. current `dj_playlist` state
4. Resolution strategy (based on `--resolve` flag):
   - `ours`: Keep DB state, ignore XML changes
   - `theirs`: Accept XML playlist structure as canonical (write to `dj_playlist`)
   - `prompt`: Show diffs, ask operator for each conflict
5. If playlists changed:
   - Update `dj_playlist` hierarchy
   - Log changes to reconciliation_log
6. If track metadata changed (cues, stars, comments):
   - Store in `dj_curation_metadata` table (new, DJ-specific notes)
   - Don't overwrite canonical enrichment (energy, key, etc.)
7. Write `dj_import_state` entry:
   - manifest_hash of source XML
   - changes_accepted (count of playlist + metadata updates)
   - conflicts_resolved (count + details)
   - timestamp

**Output**:
- Updated `dj_playlist` (if `--merge-playlists`)
- New `dj_curation_metadata` rows (operator notes + cues from Rekordbox)
- Audit trail in reconciliation_log

---

## Stage 4d: XML Validate (Quality Assurance)

**Command** (built into emit/patch; also available standalone):
```bash
poetry run tagslut dj xml validate \
  --in some_file.xml \
  --db "$TAGSLUT_DB" \
  [--fix] \
  [--report-path report.json]
```

**Checks**:
1. **XML Structure**:
   - Valid Rekordbox XML schema
   - Required elements present (COLLECTION, PLAYLISTS)
   - TrackID uniqueness within collection

2. **TrackID Mapping**:
   - All TrackIDs map back to valid (identity_id, mp3_asset_id) pairs
   - No orphaned TrackIDs (track deleted but cue points reference old ID)

3. **File References**:
   - All LOCATION paths reference valid MP3 files (or resolvable with symlink translation)
   - No broken paths (file moved/deleted since export)
   - Relative paths resolve correctly from Rekordbox working directory

4. **Metadata Consistency**:
   - All required DJ fields present (BPM, key, energy for all tracks)
   - No stale metadata (values match current canonical_payload_json)
   - Camelot key notation valid (01A–12B)

5. **Playlist Integrity**:
   - All playlist membership references valid TrackIDs
   - No duplicate tracks in playlists
   - Hierarchy is acyclic (no circular playlist refs)

**Output**:
```json
{
  "valid": true/false,
  "errors": [
    {"type": "broken_path", "track_id": 12345, "path": "...", "resolution": "file_deleted_after_export"},
    ...
  ],
  "warnings": [
    {"type": "stale_metadata", "track_id": 12345, "field": "energy", "old": "8", "new": "7"},
    ...
  ],
  "fixes_applied": ["regenerate_paths", "update_stale_metadata"],
  "report": "validation_report_2026_03_22.json"
}
```

---

## Data Structures

### dj_track_id_map Table

**Purpose**: Persistent TrackID assignment for Rekordbox cue point preservation.

**Schema**:
```sql
CREATE TABLE dj_track_id_map (
  track_id INTEGER PRIMARY KEY,                      -- Rekordbox TrackID
  identity_id INTEGER NOT NULL,                      -- track_identity row
  mp3_asset_id INTEGER NOT NULL,                     -- mp3_asset row (joined via asset_file)
  admission_id INTEGER NOT NULL,                     -- dj_admission row
  assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_emitted_at TIMESTAMP,

  FOREIGN KEY (identity_id) REFERENCES track_identity(id),
  FOREIGN KEY (mp3_asset_id) REFERENCES mp3_asset(id),
  FOREIGN KEY (admission_id) REFERENCES dj_admission(id),
  INDEX (identity_id, mp3_asset_id)
)
```

**Lifecycle**:
- Created by `dj xml emit` when assigning new TrackID
- Preserved by `dj xml patch` (TrackID never changes)
- Queried by `dj xml import` to map XML TrackID back to DB rows
- Never deleted (maintains cue point history)

---

### dj_export_state Table (Extended)

**Schema**:
```sql
CREATE TABLE dj_export_state (
  export_id INTEGER PRIMARY KEY AUTO_INCREMENT,
  manifest_hash VARCHAR(64) NOT NULL UNIQUE,         -- SHA-256
  file_path TEXT NOT NULL,
  operation_type TEXT,                               -- 'emit' or 'patch'
  profile TEXT DEFAULT 'default',                    -- 'default' or 'extended'
  path_mode TEXT DEFAULT 'absolute',                 -- 'absolute', 'relative', 'mixed'
  admission_count INTEGER,                           -- count of dj_admission in export
  playlist_count INTEGER,                            -- count of dj_playlist in export
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

  -- Validation results
  last_validated_at TIMESTAMP,
  validation_passed BOOLEAN,
  validation_errors_json TEXT,

  -- Import/round-trip tracking
  round_tripped_at TIMESTAMP,
  import_source_hash VARCHAR(64),                    -- manifest_hash of XML that was imported

  INDEX (manifest_hash),
  INDEX (created_at DESC)
)
```

---

### dj_curation_metadata Table (Proposed)

**Purpose**: Store operator-added metadata (cues, stars, notes) separate from canonical enrichment.

**Schema**:
```sql
CREATE TABLE dj_curation_metadata (
  id INTEGER PRIMARY KEY AUTO_INCREMENT,
  admission_id INTEGER NOT NULL,
  operator_notes TEXT,                               -- Freeform notes added by operator
  rekordbox_stars INTEGER,                           -- 0–5 star rating from Rekordbox
  rekordbox_color VARCHAR(6),                        -- Color tag (RGB hex)
  rekordbox_comment TEXT,                            -- Comment field from Rekordbox
  cue_points_json TEXT,                              -- Stored cue/hot cue positions (for round-trip)
  last_synced_from_rekordbox_at TIMESTAMP,

  FOREIGN KEY (admission_id) REFERENCES dj_admission(id) ON DELETE CASCADE,
  UNIQUE KEY (admission_id)
)
```

---

## Workflows

### Entire DJ Lifecycle with XML Integration

```
1. INTAKE
   tagslut intake <url>
   └─> track_identity + enrichment_state (50–80% metadata)

2. EXTEND ENRICHMENT (optional)
   lexicon_backfill
   └─> track_identity.canonical_payload_json (energy, danceability, key added)

3. BUILD MP3 LIBRARY
   mp3 build  OR  mp3 reconcile
   └─> mp3_asset (readiness='playable')

4. ADMIT TO DJ LIBRARY
   dj backfill  OR  dj admit
   └─> dj_admission (readiness='unvalidated')

5. VALIDATE
   dj validate
   └─> dj_admission.readiness='ready'  (or report errors)

6. EMIT REKORDBOX XML
   dj xml emit --out rekordbox.xml
   └─> XML written to disk
   └─> dj_export_state manifest recorded
   └─> dj_track_id_map assigned (TrackIDs persistent)

7. IMPORT TO REKORDBOX
   operator imports rekordbox.xml into Rekordbox app
   └─> operator edits playlists, cues, ratings in Rekordbox

8. ROUND-TRIP EDITS BACK TO DB (NEW)
   dj xml import --in rekordbox_curated.xml
   └─> dj_playlist updated (if --merge-playlists)
   └─> dj_curation_metadata updated (cues, ratings, notes)
   └─> audit trail recorded

9. EXPORT UPDATED XML
   dj xml patch --out rekordbox_v2.xml
   └─> Uses dj_xml_import state as baseline
   └─> Merges new DB admissions with Rekordbox edits
   └─> TrackIDs + cue points preserved
   └─> operator re-imports rekordbox_v2.xml

[REPEAT from step 7 as DJ library evolves]
```

---

## Safety Contracts

### Determinism

**Contract**: `emit` is deterministic.
- Same DB state + same profile → same XML bytes (byte-for-byte)
- Enables testing: expected XML can be pre-generated and compared

**Implementation**:
- XML output sorted by TrackID
- Timestamps excluded from XML (only in manifest hash)
- Metadata arrays ordered consistently

---

### TrackID Stability

**Contract**: TrackID assignment is stable across emit/patch/import cycles.
- Once assigned, a TrackID is never regenerated or reused
- Rekordbox cue points (beat grid, hot cues) keyed to TrackID persist

**Implementation**:
- `dj_track_id_map` is append-only (TrackIDs never deleted)
- Patch reuses prior TrackID from map
- Import preserves TrackID from XML

---

### Tamper Detection

**Contract**: Manifest hash prevents accidental overwrites and detects tampering.
- If XML is manually edited outside tagslut, patch will reject it
- If DB state diverges from XML state, patch will warn

**Implementation**:
- `dj xml patch` recomputes manifest hash from prior DB state
- Compares against stored hash; fails if mismatch
- `dj xml validate` checks for stale metadata (DB ≠ XML)

---

### Round-Trip Losslessness

**Contract**: Operator-added metadata (edits in Rekordbox) is preserved across cycles.
- Cue points, ratings, notes are not lost in emit → import → patch
- Only canonical enrichment (BPM, key, energy) is authoritative (from DB)

**Implementation**:
- `dj_curation_metadata` stores operator additions separately
- Import extracts cues, ratings, notes from XML → `dj_curation_metadata`
- Patch merges canonical enrichment + operator cues into XML
- Validate warns if canonical enrichment has drifted vs. XML

---

## Conflict Resolution Scenarios

### Scenario 1: Playlist Changes in Rekordbox

**Situation**:
- DB has playlist "[techno peaks]" with 50 tracks
- Operator in Rekordbox reorders tracks, removes 5, adds 3 new ones
- Operator exports XML from Rekordbox

**Resolution** (with `dj xml import --resolve theirs`):
- Import parses new playlist structure from XML
- Updates `dj_playlist` table to match XML
- Logs change: "reorder: +3, -5, new_order_tracked"
- Next `patch` will reflect playlist reordering

---

### Scenario 2: Stale Metadata in XML

**Situation**:
- Emit created XML with BPM=128, key=7A for track_id 12345
- Operator later runs `lexicon_backfill`, updates BPM=130, key=8A in DB
- `dj xml validate` compares DB vs. XML

**Resolution**:
- Validate reports: "metadata_stale: 50 tracks have updated BPM/key"
- `--fix` flag regenerates XML with updated metadata
- Next `patch` reflects metadata updates

---

### Scenario 3: File Path Drift

**Situation**:
- Emit created XML with path `/Volumes/MUSIC/DJ/Artist/Track.mp3`
- Files are moved to `/Volumes/MUSIC/DJ_ARCHIVE/Artist/Track.mp3`
- Rekordbox import shows broken paths

**Resolution** (with proposed `dj xml repair`):
- Scan actual MP3 library location
- Update `asset_file` with new paths
- `patch` regenerates XML with corrected paths
- Next Rekordbox import has valid paths

---

## Implementation Roadmap

### Phase 1: Strengthen Emit/Patch (Current)
- ✓ Deterministic XML generation
- ✓ Stable TrackID assignment
- ✓ Manifest hash tamper detection
- Status: Complete, tested, in production

### Phase 2: Add Validation (Week 1–2)
- Add `dj xml validate` command
- Check file references, metadata, structure
- Report stale state (DB ≠ XML)
- Status: Ready to implement

### Phase 3: Add Import (Week 3–4)
- Add `dj xml import` command
- Extract playlist structure from XML
- Store operator cues, ratings, notes
- Merge logic for conflicts
- Status: Design complete, implementation pending

### Phase 4: Extend Curation (Week 5+)
- Sync back operator edits (ratings, notes, cue points)
- Support two-way sync with Rekordbox via XML
- Add `dj gig` workflow (playlist → performance)
- Status: Post-audit future work

---

## Benefits

| Aspect | Before | After |
|--------|--------|-------|
| **Operator workflow** | tagslut DB → XML → Rekordbox (one-way) | tagslut ↔ Rekordbox via XML (bidirectional) |
| **Cue point safety** | TrackIDs regenerated on re-export (lost cues) | TrackIDs stable (cues survive) |
| **Playlist sync** | Manual (edit both DB and Rekordbox) | Automatic (XML round-trip) |
| **Validation** | None (trust export) | Comprehensive checks before/after |
| **Conflict resolution** | Manual (operator decides) | Explicit merge strategy (ours/theirs/prompt) |
| **Auditability** | Limited | Complete (export/import history) |

---

## Conclusion

Rekordbox XML should be treated as the primary interoperability boundary for DJ workflows, not just an export artifact. With emit/patch/import/validate as first-class commands, the workflow becomes:

1. **Curate in tagslut DB**: Build master identity + enrichment
2. **Admit to DJ layer**: Select which tracks go to Rekordbox
3. **Emit to XML**: Create Rekordbox-ready collection
4. **Import to Rekordbox**: Operator uses Rekordbox native editing
5. **Round-trip back**: Operator edits sync back to DB via XML import
6. **Patch and repeat**: New DJ additions merge with Rekordbox edits

This enables seamless integration with Rekordbox as the operator's primary DJ tool, while tagslut manages the canonical metadata and automation.
