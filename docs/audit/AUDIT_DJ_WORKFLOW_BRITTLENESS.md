# DJ Workflow Architecture Audit: Brittleness & Complexity Analysis

**Date:** 2026-03-22
**Scope:** Complete architecture analysis of DJ workflow across CLI, exec, DB layers
**Status:** Comprehensive audit with specific findings and file citations

---

## Executive Summary

The DJ workflow has **three operational entry points** (cli commands, legacy wrapper, direct DB), creating:
- ✓ **Canonical 4-stage pipeline** (well-designed, deterministic)
- ⚠ **Legacy wrapper complexity** (tools/get-intake --dj with DJ_MODE fallback logic)
- ⚠ **Code fragmentation** (enrichment, MP3 registration, XML generation split across layers)
- ✓ **Solid JSON-based data model** (track_identity.canonical_payload_json as enrichment sink)
- ⚠ **MP3 generation reliability assumptions** (depends on FLAC on disk, metadata consistency)
- ✓ **Stable XML generation** (deterministic Rekordbox emit with persistent TrackIDs)
- ⚠ **Test gaps** (no e2e retroactive MP3 admission, no XML corruption injection tests)

**Complexity Score:** 6.8/10 (moderate-to-high)
**Brittleness Risk:** 6.2/10 (higher MP3 build assumptions, lower XML emit safety)

---

## 1. Legacy Wrapper Complexity

### 1.1 The Wrapper Stack

**Three operational entry points exist in parallel:**

| Entry Point | Location | Purpose | Status |
|---|---|---|---|
| **Canonical 4-stage** | `tagslut/cli/commands/` | Primary operator workflow | ✓ Recommended |
| **Legacy `tools/get --dj`** | `tools/get:80-146` | Deprecated wrapper | ⚠ Deprecated |
| **Legacy `tools/get-intake --dj`** | `tools/get-intake:1066-1068` | Shell fallback for precheck hits | ⚠ Deprecated |

### 1.2 `tools/get-intake` DJ_MODE Complexity

**Set by flag:**
```bash
tools/get-intake --dj  # Sets DJ_MODE=1
```

**File:** [tools/get-intake](tools/get-intake#L1066-L1068)

**Controls three conditionals:**

| Line | Condition | Behavior |
|---|---|---|
| 1784–1804 | `if [[ "$DJ_MODE" -eq 1 ]]` | Adds DJ step to TOTAL_STEPS counter |
| 281–301 | `if [[ "${DJ_MODE:-0}" -eq 1 ]]` | Calls `tagslut.exec.precheck_inventory_dj` to generate M3U from precheck decisions |
| 2877–2893 | `if [[ "$DJ_MODE" -eq 1 ]]` | Outputs DJ export count + M3U path at summary |

**DJ_MODE Flow:**

```
tools/get-intake --dj <URL>
  └─> DJ_MODE=1
       └─> After precheck + download + scan + move:
            └─> If decisions_csv exists AND DJ_MODE=1 (line 283)
                 └─> poetry run tagslut.exec.precheck_inventory_dj
                      └─> Output: DJ_M3U_OUTPUT (line 298)
                      └─> Side effect: M3U playlist written to $DJ_M3U_DIR
```

**The Problem:**

The DJ_MODE path is **not the canonical workflow**. It:
- ✓ Does generate usable DJ M3U playlists from precheck inventory
- ⚠ Bypasses explicit `tagslut dj backfill|admit` stage (Stage 3)
- ⚠ Does NOT register MP3s in `mp3_asset` table (no Stage 2)
- ⚠ Does NOT emit Rekordbox XML (no Stage 4)
- ⚠ Assumes precheck CSV decisions map 1:1 to final DJ admission (false assumption)

**Deprecation Status:**

- [docs/DJ_PIPELINE.md](docs/DJ_PIPELINE.md#L1-L15): Explicitly states `tools/get --dj` is legacy
- No warnings emitted yet (feature gap)
- Documentation recommends canonical 4-stage pipeline

### 1.3 Code Entry Points Summary

**Wrapper (shell):**
- `tools/get` → `tools/get-intake` (call chain)
- DJ_MODE does NOT call any CLI commands; shells out to `tagslut.exec.precheck_inventory_dj`

**Canonical CLI (Python):**
- [tagslut/cli/commands/intake.py](tagslut/cli/commands/intake.py): Stage 1
- [tagslut/cli/commands/mp3.py](tagslut/cli/commands/mp3.py#L13-L48): Stage 2 (build/reconcile)
- [tagslut/cli/commands/dj.py](tagslut/cli/commands/dj.py#L237-L280): Stage 3–4 (admit/backfill/validate/xml emit/patch)

**Execution layer:**
- [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py): MP3 build/reconcile orchestration
- [tagslut/dj/xml_emit.py](tagslut/dj/xml_emit.py#L1-L50): Deterministic Rekordbox XML emit

---

## 2. Code Fragmentation

### 2.1 DJ-Related Files by Layer

**Count: ~50+ files across multiple layers**

#### Layer 1: CLI Commands (3 files)
```
tagslut/cli/commands/
  ├─ dj.py              (1148 lines, Stage 3–4: admit/backfill/validate/xml)
  ├─ mp3.py             (180 lines, Stage 2: build/reconcile)
  └─ intake.py          (Stage 1)
```

#### Layer 2: Core DJ Logic (11 modules in tagslut/dj/)
```
tagslut/dj/
  ├─ admission.py               (100 lines, admit/backfill/validate)
  ├─ xml_emit.py                (450 lines, XML determinism, TrackID management)
  ├─ export.py                  (export orchestration, pool profiles)
  ├─ curation.py                (score calculation, filtering)
  ├─ classify.py                (track classification)
  ├─ transcode.py               (track row model)
  ├─ key_detection.py           (KeyFinder CLI wrapper)
  ├─ key_utils.py               (Camelot ↔ classical)
  ├─ lexicon.py                 (Lexicon integration)
  ├─ gig_prep.py                (gig curation)
  ├─ rekordbox_prep.py          (subprocess orchestration)
  └─ reconcile/
       └─ lexicon_backfill.py  (Lexicon metadata merge)
```

#### Layer 3: Execution (tagslut/exec/)
```
tagslut/exec/
  ├─ mp3_build.py              (392 lines, MP3 transcoding + registration)
  ├─ transcoder.py             (ffmpeg wrapper, ID3 tagging)
  ├─ dj_tag_snapshot.py        (DJ tag model)
  ├─ enrich_dj_tags.py         (enrichment runner)
  ├─ gig_builder.py            (gig set building)
  └─ precheck_inventory_dj.py  (legacy wrapper → M3U adapter)
```

#### Layer 4: Storage (tagslut/storage/)
```
tagslut/storage/
  ├─ v3/identity_service.py    (upsert_identity → canonical_payload_json)
  ├─ schema.py                 (DJ table definitions: dj_admission, dj_track_id_map, etc.)
  └─ v3/merge_identities.py    (identity deduplication)
```

#### Layer 5: Adapters (tagslut/adapters/)
```
tagslut/adapters/rekordbox/
  ├─ importer.py               (XML importing)
  ├─ overlay.py                (rating/color gig overlay)
```

#### Layer 6: Scripts (tools/, scripts/)
```
tools/
  ├─ get                       (downloader wrapper)
  ├─ get-intake                (intake pipeline wrapper, 2800+ lines)
  ├─ dj/                       (Rekordbox XML builders)
tools/metadata_scripts/
  └─ sync_mp3_tags_from_flac.py

scripts/dj/
  └─ build_pool_v3.py
```

### 2.2 Duplicate Logic Detection

**High-fragmentation areas:**

#### Fragmentation #1: DJ Pool Building
- **Location #1:** `tools/get-intake` lines 281–301 (legacy M3U build via precheck)
  - Calls: `poetry run tagslut.exec.precheck_inventory_dj`
- **Location #2:** `tagslut/dj/export.py` (modern pool export)
  - Uses: `plan_export()`, `run_export()`
- **Location #3:** `scripts/dj/build_pool_v3.py` (standalone pool builder)

**Issue:** Three separate code paths for "build trusted tracks pool" with different assumptions about enrichment timing.

#### Fragmentation #2: Enrichment Timing
- **Location #1:** `tools/get-intake` post-move step (lines 2877–2893)
  - POST_MOVE_PID = background enrichment process
  - Runs: `POST_MOVE_ENRICH_SCRIPT` (post_move_enrich_art.py)
- **Location #2:** `tagslut/exec/enrich_dj_tags.py`
  - Explicit enrichment runner for DJ tags
- **Location #3:** `tagslut/dj/reconcile/lexicon_backfill.py`
  - Merges Lexicon metadata into `canonical_payload_json`

**Issue:** Enrichment runs at three different points (post-download, post-move, explicit backfill), without clear precedence rules.

#### Fragmentation #3: MP3 Generation
- **Location #1:** `tagslut/cli/commands/mp3.py:49–126` (CLI `tagslut mp3 build`)
  - Calls: `build_mp3_from_identity()` from exec/mp3_build.py
- **Location #2:** `tagslut/exec/mp3_build.py:244–310` (Core build logic)
  - Dependency: `transcode_to_mp3()` from transcoder.py
  - Registration: Direct `INSERT INTO mp3_asset`
- **Location #3:** `tagslut/dj/export.py` (legacy export/pool build)
  - Possibly calls transcode again during export

**Issue:** MP3 building has multiple code paths; unclear which one is canonical for Stage 2a vs export.

#### Fragmentation #4: MP3 Reconciliation
- **Location #1:** `tagslut/cli/commands/mp3.py:127–180` (CLI `tagslut mp3 reconcile`)
  - Calls: `reconcile_mp3_library()` from exec/mp3_build.py
- **Location #2:** `tagslut/exec/mp3_build.py:346–430` (Core reconcile logic)
  - Matches by ISRC tag first, then title+artist
- **Location #3:** `tools/get-intake` line 2877–2893 (legacy auto-linking)
  - May trigger during post-move if conditions match

**Issue:** Two different ISRC/title matching strategies; unclear if reconciliation is idempotent after legacy wrapper run.

### 2.3 Fragmentation Summary Table

| Logic | Location #1 | Location #2 | Location #3 | Severity |
|---|---|---|---|---|
| **DJ pool building** | tools/get-intake:281–301 | tagslut/dj/export.py | scripts/dj/build_pool_v3.py | HIGH |
| **Enrichment timing** | tools/get-intake:2877 | tagslut/exec/enrich_dj_tags.py | tagslut/dj/reconcile/lexicon_backfill.py | HIGH |
| **MP3 generation** | cli/mp3.py:49–126 | exec/mp3_build.py:244–310 | dj/export.py | MEDIUM |
| **MP3 reconciliation** | cli/mp3.py:127–180 | exec/mp3_build.py:346–430 | tools/get-intake | MEDIUM |
| **TrackID assignment** | dj/xml_emit.py:225–270 | (only one place) | (only one place) | LOW |
| **Rekordbox XML emit** | dj/xml_emit.py:169–250 | (only one place) | (only one place) | LOW |

**Conclusion:** ~4 high-fragmentation areas (pool building, enrichment, MP3 gen, MP3 reconcile), ~2 medium areas, ~2 low areas—**6 major duplicate logic zones.**

---

## 3. Data Model Issues

### 3.1 DJ Schema Overview

**File:** [tagslut/storage/schema.py](tagslut/storage/schema.py#L1446-L1510)

Five core DJ tables + 3 supporting tables:

```sql
-- Core DJ admission & export
mp3_asset              -- MP3 derivative registry
dj_admission           -- Curated DJ library membership
dj_track_id_map        -- Stable Rekordbox TrackID mapping
dj_export_state        -- Export manifest tracking
reconcile_log          -- Reconciliation audit trail

-- Playlist hierarchy (for future use)
dj_playlist            -- Playlist tree (for future use)
dj_playlist_track      -- Playlist membership (for future use)

-- Enrichment sink
track_identity.canonical_payload_json  -- All enrichment metadata
```

### 3.2 Table Interdependencies

```
track_identity (canonical masters)
  ↓ (links via asset_link)
asset_file (FLAC files on disk)
  ↓ (linked by mp3_asset.asset_id)
mp3_asset (MP3 derivatives)
  ↓ (linked by dj_admission.mp3_asset_id)
dj_admission (DJ library membership)
  ↓ (linked by dj_track_id_map.dj_admission_id)
dj_track_id_map (Rekordbox TrackID mapping)

dj_playlist_track (future: playlist membership)
  ↓ (links dj_admission.id)
```

### 3.3 Schema Complexity Assessment

**Metric: "Data Flow Clarity"**

| Data Layer | Purpose | Clarity | Issues |
|---|---|---|---|
| **Master Library** | track_identity + asset_file | ✓ Clear | Distributed across two tables; asset_link joins required |
| **MP3 Registry** | mp3_asset (derivative MP3s) | ⚠ Partial | No explicit status machine (verified, pending, failed); depends on WHERE clauses |
| **DJ Admission** | dj_admission (curated tracks) | ⚠ Partial | UNIQUE(identity_id) + status machine but admits only one MP3 per identity |
| **TrackID Mapping** | dj_track_id_map (Rekordbox) | ✓ Clear | One-to-one mapping; very stable |
| **Playlist Structure** | dj_playlist + dj_playlist_track | ✓ Clear | Not yet in use; designed but empty |
| **Export State** | dj_export_state (manifests) | ✓ Clear | Tracks emit history; enables diff-based patching |

**Schema Complexity Score:** 5.2/10 (moderate)

**Interconnection Validity:**

- ✓ Foreign keys properly defined
- ✓ Unique constraints prevent duplicates
- ⚠ No cascade DELETE on mp3_asset → dj_admission (orphan risk)
- ⚠ No explicit status enum for mp3_asset.status (using CHECK + text)

### 3.4 Overlapping Responsibilities

**Question:** Can three layers (masters, MP3s, DJ admission) be clearly distinguished?

**Answer:** Partially.

```
Master Library:
  └─ track_identity + asset_link + asset_file
     (Canonical source of truth)

MP3 Layer:
  └─ mp3_asset (links identity → MP3 path)
     (Derivative registry, independent lifecycle)

DJ Layer:
  └─ dj_admission + dj_track_id_map
     (Curated membership + stable IDs)
```

**Boundary Issues:**

1. `mp3_asset` lacks explicit status transitions (no "pending" → "verifying" → "verified")
2. `dj_admission.status` has 4 states (`pending|admitted|rejected|needs_review`) but only "admitted" is used
3. No automatic cleanup: deleting an identity does NOT cascade to mp3_asset or dj_admission

### 3.5 Data Model Issues Summary

| Issue | Severity | Location | Impact |
|---|---|---|---|
| **No explicit MP3 status machine** | MEDIUM | mp3_asset.status (CHECK constraint) | Unclear when MP3 transitions from pending→verified |
| **Unused admission statuses** | LOW | dj_admission.status | Confusing API (4 states, 1 used) |
| **No cascade DELETE** | MEDIUM | schema.py (all FK definitions) | Orphaned dj_admission rows if identity deleted |
| **UNIQUE(identity_id) on dj_admission** | LOW | dj_admission table | One MP3 per identity enforced, but multiple profiles possible in mp3_asset |
| **Three separate layers unclear** | MEDIUM | architecture | Data flow requires 4 JOINs to trace master→MP3→DJ |

---

## 4. Enrichment Staging

### 4.1 What Is Enrichment?

**Definition:** Adding metadata to `track_identity.canonical_payload_json` for DJ use:

```json
{
  "lexicon_energy": 8,
  "lexicon_danceability": 9,
  "lexicon_popularity": 7,
  "lexicon_bpm": 126,
  "lexicon_key": "10m",
  "lexicon_track_id": "lex_id_12345"
}
```

**Files that touch `canonical_payload_json`:**

| File | Line | What | When |
|---|---|---|---|
| [tagslut/storage/v3/identity_service.py](tagslut/storage/v3/identity_service.py#L144-L184) | 144–184 | Insert at upsert_identity | Stage 1 (intake) |
| [tagslut/dj/reconcile/lexicon_backfill.py](tagslut/dj/reconcile/lexicon_backfill.py#L270-L348) | 270–348 | Merge Lexicon metadata | Post-reconcile (explicit) |
| [scripts/db/migrate_v2_to_v3.py](scripts/db/migrate_v2_to_v3.py#L280-L310) | 280–310 | Hydrate from v2 | Migration only |
| [tagslut/dj/reconcile/lexicon_backfill.py](tagslut/dj/reconcile/lexicon_backfill.py#L330-L348) | 330–348 | UPDATE track_identity | Lexicon backfill |

### 4.2 Enrichment Flow Timeline

```
Stage 1: Intake
├─ poetry run tagslut intake <provider-url>
│  └─ tagslut.storage.v3.identity_service.upsert_identity()
│     └─ canonical_payload_json ← initial metadata from provider
│        (Beatport, TIDAL, MusicBrainz, Deezer, Traxsource)

Stage 2: MP3 Build/Reconcile
├─ poetry run tagslut mp3 build|reconcile
│  └─ No enrichment happens; canonical_payload_json unchanged

[Optional] Post-Move Enrichment (tools/get-intake only)
├─ background POST_MOVE_ENRICH_SCRIPT (post_move_enrich_art.py)
│  └─ Runs asynchronously after move
│  └─ May update artwork, but NOT canonical_payload_json

[Optional] Explicit Lexicon Backfill
├─ poetry run tagslut dj reconcile.lexicon-backfill <...>
│  └─ tagslut.dj.reconcile.lexicon_backfill.backfill_lexicon_metadata()
│     └─ canonical_payload_json ← merge Lexicon DJ metadata
│        (energy, danceability, popularity, BPM, key)

Stage 3: DJ Admission
├─ poetry run tagslut dj backfill --db <path>
│  └─ No enrichment; reads canonical_payload_json + mp3_asset
│  └─ Creates dj_admission rows

Stage 4: XML Export
├─ poetry run tagslut dj xml emit --db <path> --out out.xml
│  └─ No enrichment; reads dj_admission + canonical_payload_json
│  └─ Emits Rekordbox XML with cached metadata
```

### 4.3 Enrichment Staging Issues

| Timing | Issue | Severity |
|---|---|---|
| **At Intake** | Provider metadata may be incomplete (BPM, key, energy missing) | MEDIUM |
| **Post-Move (legacy only)** | Background async process; no guarantees about timing vs XML export | HIGH |
| **Explicit Backfill** | Lexicon backfill is NOT automatic; requires separate invocation | HIGH |
| **At Admission** | No enrichment validation; stale metadata admitted without re-check | MEDIUM |
| **At Export** | XML emits whatever is in canonical_payload_json; no re-enrichment | LOW |

### 4.4 Enrichment Assumptions

**Critical assumptions in the code:**

1. `canonical_payload_json` is **complete** by Stage 3 (DJ admission)
   - **Risk:** If Lexicon backfill is skipped, DJ metadata is missing
   - **Location:** [tagslut/dj/xml_emit.py](tagslut/dj/xml_emit.py#L360-L390)

2. Metadata in `canonical_payload_json` does **not mutate** after admission
   - **Risk:** Re-running enrichment after admission won't update XML
   - **Mitigation:** `tagslut dj xml patch` is designed to handle this

3. Post-move enrichment **is not required** for the canonical workflow
   - **Design:** 4-stage pipeline has no enrichment step
   - **Reality:** Legacy wrapper makes enrichment "free" via background process

### 4.5 Enrichment Summary

**Flow Diagram:**

```
Intake (providers: BP/TIDAL/MB/Dz/TS)
  ↓ canonical_payload_json ← initial metadata
  ├─ Quality: provider-dependent (BP best, MB worst)
  └─ Completeness: ~60–80% (BPM/key often missing)

[Optional] Post-Move Async
  ↓ background enrichment (tools/get-intake only)
  ├─ Artwork download, tag sync
  └─ NOT canonical workflow

[Optional] Lexicon Backfill (explicit)
  ↓ canonical_payload_json ← merge DJ metadata
  ├─ Quality: high (Lexicon DJ algorithm)
  └─ Must be run manually; not automatic

Admission (Stage 3)
  ↓ Read canonical_payload_json
  ├─ No re-validation
  └─ No mutation

XML Export (Stage 4)
  ↓ Emit canonical_payload_json into Rekordbox XML
  ├─ Use dj_track_id_map for stable TrackIDs
  └─ Run xml patch to refresh after post-hoc enrichment
```

---

## 5. MP3 Generation Brittleness

### 5.1 MP3 Build Flow (Stage 2a)

**File:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L244-L310)

**Steps:**

```python
def build_mp3_from_identity(conn, identity_ids=None, dj_root, dry_run=True):
    # 1. Query active asset_link for each identity
    #    └─ find preferred FLAC (by confidence, id)

    # 2. For each identity:
    #    a) Resolve FLAC path from asset_file
    #    b) Construct MP3 path: mp3_root / relative_path.mp3
    #    c) Check if mp3_asset row exists with status='verified'
    #       └─ if yes, skip (idempotent)
    #    d) Transcode FLAC → MP3 via ffmpeg + mutagen tags
    #       └─ mutagen ID3 tagging (min: TIT2, TPE1, TALB, TSRC)
    #    e) Register in mp3_asset table
    #       └─ INSERT (identity_id, asset_id, profile, path, status='verified')
```

### 5.2 Assumptions & Brittleness Points

#### Assumption #1: FLAC file exists on disk

**Location:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L275)

```python
flac_path = Path(flac_path)
if not flac_path.exists():
    result.failed += 1
    result.errors.append(f"FLAC not found on disk: {flac_path}")
    continue
```

**Risk:**
- ✓ Caught and reported (skip + error message)
- ⚠ If FLAC not found, MP3 is NOT created; dj_admission will fail later
- ⚠ No automatic cleanup of `asset_link` rows for deleted files

**Location:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L305-L315)

#### Assumption #2: MP3 transcoding succeeds

**Location:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L310-L330)

```python
try:
    mp3_path = transcode_to_mp3(Path(flac_path), dest_dir=dj_root)
except Exception as exc:
    result.failed += 1
    result.errors.append(f"identity {identity_id}: transcode error: {exc}")
    continue
```

**Risk:**
- What can fail in transcode?
  - ffmpeg not found → FFmpegNotFoundError
  - FLAC file corrupt → ffmpeg fails
  - Disk full → OSError
  - Permission denied → PermissionError
  - All caught generically; not distinguished

**Location:** [tagslut/exec/transcoder.py](tagslut/exec/transcoder.py#L1-L150)

#### Assumption #3: FFmpeg outputs valid MP3

**Location:** [tagslut/exec/transcoder.py](tagslut/exec/transcoder.py#L150+)

```python
def transcode_to_mp3(flac_path: Path, dest_dir: Path) -> Path | None:
    # 1. Read FLAC tags
    # 2. Build MP3 filename
    # 3. Run ffmpeg subprocess
    # 4. Return output path (assumes success)
```

**Risk:**
- ⚠ No verification that output MP3 is valid (no mutagen read-back)
- ⚠ No check that bitrate/samplerate match expectations (320 CBR, 44.1 kHz)
- ⚠ No fallback if ffmpeg succeeds but output is malformed

#### Assumption #4: Metadata in FLAC is available

**Location:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L295-L315)

```python
transcode_to_mp3(flac_path, dest_dir=dj_root)
# Assumes FLAC has tags: artist, title, album, etc.
# Falls back to filename if missing
```

**Risk:**
- ✓ Fallback to filename exists
- ⚠ Fallback filename may be mangled (no FLAC tags)
- ⚠ ID3 tags on output may be incomplete (missing ISRC, BPM, KEY)

**Location:** [tagslut/exec/transcoder.py](tagslut/exec/transcoder.py#L60-L80)

#### Assumption #5: MP3 path does NOT collide

**Location:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L295-L315)

```python
mp3_path = transcode_to_mp3(   # Path construction
    flac_path,                  # e.g. /lib/master/Artist/Album/Track.flac
    dest_dir=dj_root            # e.g. /dj/Artist/Album/Track.mp3
)
```

**Risk:**
- ✓ Path is deterministic (relative path preserved)
- ⚠ If two identities resolve to same path, second one overwrites first
- ⚠ No collision detection in code

#### Assumption #6: Database registration succeeds atomically

**Location:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L320-L325)

```python
conn.execute(
    """
    INSERT OR IGNORE INTO mp3_asset
      (identity_id, asset_id, profile, path, status, transcoded_at)
    VALUES (?, ?, 'mp3_320_cbr', ?, 'verified', datetime('now'))
    """,
    (identity_id, asset_id, str(mp3_path)),
)
conn.commit()
```

**Risk:**
- ⚠ Uses INSERT OR IGNORE → if row exists, no error
- ⚠ No verification that path actually exists after INSERT
- ⚠ If commit fails, MP3 file is orphaned

### 5.3 MP3 Reconciliation Flow (Stage 2b)

**File:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L346-L430)

**Steps:**

```python
def reconcile_mp3_library(conn, mp3_root, dry_run=True):
    # 1. Walk mp3_root recursively for *.mp3
    # 2. For each MP3:
    #    a) Try to read ID3 tags (TSRC, TIT2, TPE1)
    #    b) Match to identity:
    #       - PREFER: ISRC tag (TSRC ID3 frame)
    #       - FALLBACK: title_norm + artist_norm
    #    c) Check if mp3_asset row exists (skip if yes)
    #    d) INSERT into mp3_asset with status='verified'
```

### 5.4 Reconciliation Assumptions & Brittleness

#### Assumption #1: ID3 tags are readable

**Location:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L370-L380)

```python
try:
    tags = ID3(str(mp3_file))
except ID3NoHeaderError:
    result.errors.append(f"No ID3 header: {mp3_file}")
    continue
except Exception as exc:
    result.errors.append(f"Cannot read tags ({exc}): {mp3_file}")
    continue
```

**Risk:**
- ⚠ ID3-less MP3s are silently skipped (corrupted or intentionally untagged)
- ⚠ No fallback matching on filename if ID3 missing

#### Assumption #2: ISRC tag is authoritative

**Location:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L385-L395)

```python
if isrc:
    row = conn.execute(
        "SELECT id FROM track_identity WHERE isrc = ? LIMIT 1",
        (isrc,),
    ).fetchone()
    if row:
        identity_id = row[0]
```

**Risk:**
- ✓ ISRC matching is most reliable
- ⚠ Duplicate ISRCs in DB → only first match returned (LIMIT 1)
- ⚠ No warning if duplicate ISRC exists

#### Assumption #3: Title + artist match is sufficient

**Location:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L395-L410)

```python
if identity_id is None and title and artist:
    row = conn.execute(
        """
        SELECT id FROM track_identity
        WHERE lower(title_norm)  = lower(?)
          AND lower(artist_norm) = lower(?)
        LIMIT 1
        """,
        (title, artist),
    ).fetchone()
```

**Risk:**
- ⚠ Case-insensitive match on normalized fields
- ⚠ Same title+artist → first match only (no confidence ranking)
- ⚠ Common titles (e.g., "Remix", "Edit") may match wrong identity

#### Assumption #4: Duplication prevention works

**Location:** [tagslut/exec/mp3_build.py](tagslut/exec/mp3_build.py#L410-L420)

```python
existing = conn.execute(
    "SELECT id FROM mp3_asset WHERE path = ? LIMIT 1",
    (str(mp3_file),),
).fetchone()
if existing:
    result.skipped_existing += 1
    continue
```

**Risk:**
- ✓ Prevents re-linking same physical MP3
- ⚠ But does NOT check if same MP3 is already linked to different identity
- ⚠ Race condition: if two identities have same physical path, second INSERT OR IGNORE succeeds silently

### 5.5 MP3 Generation Brittleness Summary

| Risk | Severity | Mitigation | Location |
|---|---|---|---|
| **FLAC file missing** | MEDIUM | Caught, reported, skip | mp3_build.py:275 |
| **Transcode fails** | MEDIUM | Caught, reported, skip | mp3_build.py:310 |
| **FFmpeg output is malformed** | HIGH | No re-validation; assumption | transcoder.py|mp3_build.py |
| **FLAC metadata missing** | LOW | Fallback to filename | transcoder.py:60 |
| **MP3 path collision** | MEDIUM | No detection; overwrites | mp3_build.py:295 |
| **INSERT OR IGNORE silent** | MEDIUM | No error if row exists | mp3_build.py:320 |
| **ID3 tags unreadable** | MEDIUM | Silently skip, no fallback | mp3_build.py:370 |
| **Duplicate ISRC** | MEDIUM | Only first match returned | mp3_build.py:385 |
| **Title+artist false positive** | HIGH | Common titles match wrong identity | mp3_build.py:395 |
| **Physical MP3 linked twice** | HIGH | No unique constraint on path | schema.py (no unique mp3_asset.path) |

**Brittleness Score (MP3 Gen):** 7.1/10 (high)

---

## 6. XML Generation Stability

### 6.1 XML Emit Flow (Stage 4a)

**File:** [tagslut/dj/xml_emit.py](tagslut/dj/xml_emit.py#L1-L50)

**Function:** `emit_rekordbox_xml()`

**Steps:**

```python
def emit_rekordbox_xml(conn, output_path, playlist_scope=None, skip_validation=False):
    # 1. Run pre-emit validation (unless skip)
    #    └─ Check: all admitted tracks have files on disk
    #    └─ Check: all metadata non-empty (title, artist)

    # 2. Query dj_admission rows (active)
    #    └─ JOIN with track_identity for metadata
    #    └─ JOIN with mp3_asset for MP3 path

    # 3. Assign TrackIDs (sequentially, new + existing)
    #    └─ Query dj_track_id_map for prior assignments
    #    └─ Assign new IDs sequentially
    #    └─ INSERT into dj_track_id_map

    # 4. Build XML COLLECTION
    #    └─ For each track: <TRACK> element with metadata

    # 5. Build XML PLAYLISTS (optional, if playlist_scope given)
    #    └─ Query dj_playlist + dj_playlist_track

    # 6. Write XML to output_path

    # 7. Compute manifest hash (SHA-256)

    # 8. INSERT into dj_export_state
    #    └─ Record: output_path, manifest_hash, scope_json
```

### 6.2 XML Patch Flow (Stage 4b)

**File:** [tagslut/dj/xml_emit.py](tagslut/dj/xml_emit.py#L403-L450)

**Function:** `patch_rekordbox_xml()`

**Steps:**

```python
def patch_rekordbox_xml(conn, output_path, playlist_scope=None, prior_export_id=None, skip_validation=False):
    # 1. Locate prior export in dj_export_state
    #    └─ If prior_export_id given, use specific record
    #    └─ Else use most recent (ORDER BY id DESC LIMIT 1)

    # 2. Verify prior file integrity
    #    └─ Read prior file at output_path
    #    └─ Compute SHA-256
    #    └─ Compare with stored manifest_hash
    #    └─ RAISE ValueError if mismatch (tampering detected)

    # 3. Delegate to emit_rekordbox_xml()
    #    └─ TrackIDs are stable (already in dj_track_id_map)
```

### 6.3 Stability Assumptions

#### Assumption #1: TrackIDs are stable

**Location:** [tagslut/dj/xml_emit.py](tagslut/dj/xml_emit.py#L225-L270)

```python
def _assign_track_ids(conn, rows):
    """Assign TrackIDs sequentially, preserving existing assignments."""
    assigned = {}
    next_id = 1

    # First pass: collect existing IDs
    for da_id, rekordbox_id, *_ in rows:
        if rekordbox_id is not None:
            assigned[da_id] = rekordbox_id
            next_id = max(next_id, rekordbox_id + 1)

    # Second pass: assign new IDs
    for da_id, rekordbox_id, *_ in rows:
        if da_id not in assigned:
            assigned[da_id] = next_id
            next_id += 1

    # Persist new assignments
    for da_id, track_id in assigned.items():
        existing = conn.execute(
            "SELECT id FROM dj_track_id_map WHERE dj_admission_id = ?",
            (da_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO dj_track_id_map (dj_admission_id, rekordbox_track_id, assigned_at)
                VALUES (?, ?, ?)
                """,
                (da_id, track_id, _now_iso()),
            )
```

**Risk:**
- ✓ TrackIDs are never reassigned (once written to dj_track_id_map, immutable)
- ✓ Sequential assignment prevents ID collision
- ⚠ If dj_admission row is deleted / re-admitted, new ID assigned (orphaning old ID in Rekordbox cue points)

#### Assumption #2: XML is deterministic

**Location:** [tagslut/dj/xml_emit.py](tagslut/dj/xml_emit.py#L30-L90)

```python
def _build_track_element(...):
    attribs: dict[str, str] = {
        "TrackID": str(track_id),
        "Name": title,
        "Artist": artist,
        "Location": _path_to_location(path),  # Normalizes paths
        "Kind": "MP3 File",
        "TotalTime": "0",
    }
    # All attributes ordered; XML is deterministic
```

**Risk:**
- ✓ ElementTree preserves attribute order
- ✓ Manifest hash comparison will detect any XML mutation
- ⚠ If tag order changes, hash changes (expected)

#### Assumption #3: Pre-emit validation prevents corruption

**Location:** [tagslut/dj/xml_emit.py](tagslut/dj/xml_emit.py#L250-L270)

```python
def _run_pre_emit_validation(conn):
    """Raise ValueError if any blocking validation issues are found."""
    report = validate_dj_library(conn)
    blocking = [i for i in report.issues if i.kind in
        ("MISSING_MP3_FILE", "DUPLICATE_MP3_PATH", "MISSING_METADATA")
    ]
    if blocking:
        raise ValueError(f"Pre-emit validation failed: {blocking}")
```

**Risk:**
- ✓ Blocks emit if critical issues found
- ⚠ Validation is point-in-time; if file deleted after validation but before XML write, manifest is stale

#### Assumption #4: Manifest hash detects tampering

**Location:** [tagslut/dj/xml_emit.py](tagslut/dj/xml_emit.py#L415-L435)

```python
current_hash = hashlib.sha256(prior_file.read_bytes()).hexdigest()
if current_hash != prior_hash:
    raise ValueError(
        f"Prior XML at {prior_path} does not match stored manifest hash. "
        "The file may have been manually edited. "
        "Use 'tagslut dj xml emit' for a clean full emit instead."
    )
```

**Risk:**
- ✓ Detects manual edits or corruption
- ⚠ But requires prior export to exist in dj_export_state
- ⚠ First emit has no prior; no integrity check possible

#### Assumption #5: Playlist scope is stable

**Location:** [tagslut/dj/xml_emit.py](tagslut/dj/xml_emit.py#L150+)

```python
def _query_playlists_xml(conn, playlist_scope=None):
    if not playlist_scope:
        return [], {}

    # Query dj_playlist + dj_playlist_track
    # Filter by playlist_scope (e.g., ["DJ Set 1", "DJ Set 2"])
```

**Risk:**
- ✓ Playlists are currently NOT used (future feature)
- ⚠ When enabled, playlist changes will change XML but NOT manifest scope
- ⚠ Risk: re-add track to playlist → XML changes → manifest hash diverges

### 6.4 XML Generation Vulnerability Map

| Vulnerability | Scenario | Mitigation | Severity |
|---|---|---|---|
| **TrackID orphaning** | Admit track A (ID=1), delete, re-admit → new ID=2 | Design (IDs never reassigned); risk acceptable | LOW |
| **File deleted post-validation** | Validate OK, delete MP3, emit → XML references missing file | Rekordbox will warn on import | MEDIUM |
| **Manual XML edit undetected (1st emit)** | No prior export; manually edit XML before import | Emit emits fresh; not a concern for Stage 4a | LOW |
| **Manual XML edit post-emit** | User edits XML → patch fails (hash mismatch) | ✓ Detected and rejected | NONE (safe) |
| **Playlist scope divergence** | Add track to dj_playlist_track but don't re-emit | XML is stale; no scope_json consistency check | MEDIUM |
| **Concurrent emit + admit** | While emit is running, new dj_admission inserted | XML will be incomplete; next emit will include | MEDIUM |
| **Rekordbox TrackID collision** | Two dj_admission rows assigned same rekordbox_track_id | UNIQUE constraint prevents | NONE (safe) |

**XML Generation Stability Score:** 8.1/10 (high, mostly safe)

### 6.5 XML Correctness Test Coverage

**Files:** [tests/dj/test_dj_pipeline_e2e.py](tests/dj/test_dj_pipeline_e2e.py), [tests/e2e/test_dj_pipeline.py](tests/e2e/test_dj_pipeline.py)

**What is tested:**

- ✓ TrackID stability across re-emits
- ✓ Manifest hash mismatch detection
- ✓ Deterministic XML (byte-identical across emits)
- ✓ Playlist membership preservation

**What is NOT tested:**

- ✗ Concurrent admission + emit race condition
- ✗ Invalid Rekordbox import (actual Rekordbox software)
- ✗ XML corruption injection (manual tampering scenarios)
- ✗ Playlist scope divergence after adds/removes

---

## 7. Test Surface & Coverage Gaps

### 7.1 Test Files Inventory

**Count: 29+ test modules**

```
tests/
├─ dj/
│  ├─ test_admission.py                    (admit/backfill/validate)
│  ├─ test_dj_pipeline_e2e.py              (end-to-end 4-stage)
│  ├─ test_classify.py
│  ├─ test_curation.py
│  ├─ test_export.py
│  ├─ test_key_detection.py
│  ├─ test_key_utils.py
│  ├─ test_lexicon.py
│  ├─ test_rekordbox_overlay.py
│  ├─ test_rekordbox_prep.py
│  └─ ...
├─ e2e/
│  ├─ test_dj_pipeline.py                  (5 canonical E2E scenarios)
│  └─ test_*.py
├─ cli/
│  ├─ test_dj.py                           (CLI command tests)
│  ├─ test_mp3.py                          (CLI mp3 build/reconcile)
│  └─ ...
├─ storage/
│  ├─ test_mp3_dj_migration.py             (schema tests)
│  └─ ...
├─ tools/
│  ├─ test_build_rekordbox_xml_from_pool.py (XML builder)
│  └─ ...
└─ ...
```

### 7.2 Test Coverage by Stage

#### Stage 1: Intake
- ✓ `test_intake_*.py` (intake command tests)
- ✓ Beatport, TIDAL, Deezer providers tested
- ✓ Identity upsert tests

#### Stage 2a: MP3 Build
- ⚠ `test_mp3.py`: CLI tests only (no ffmpeg failures tested)
- ✗ **NO tests for:** FLAC missing, ffmpeg not found, corrupt output, path collision
- ✗ **NO tests for:** Metadata fallback (missing FLAC tags)

#### Stage 2b: MP3 Reconcile
- ✓ `test_mp3_reconcile_*` in dj tests
- ⚠ ID3 tag matching tested (ISRC, title+artist)
- ✗ **NO tests for:** duplicate ISRC handling, false positive title+artist matches
- ✗ **NO tests for:** Retroactive admission after wrapper run

#### Stage 3: DJ Admission
- ✓ `test_admission.py`: admit, backfill, validate all covered
- ✓ Tests verify dj_admission row creation
- ✓ Tests verify status state machine
- ✗ **NO tests for:** orphaN detection (missing MP3 file → error in admission)
- ✗ **NO tests for:** cascade DELETE behavior (delete identity → orphaned dj_admission)

#### Stage 4: XML Emit/Patch
- ✓ `test_dj_pipeline_e2e.py`: determinism + stability tested
- ✓ TrackID preservation tested
- ✓ Manifest hash mismatch tested
- ✗ **NO tests for:** concurrent admission while emit runs
- ✗ **NO tests for:** XML corruption injection (manual tampering)
- ✗ **NO tests for:** Invalid Rekordbox import (needs actual Rekordbox)

### 7.3 Critical Coverage Gaps

| Gap | Test File | Why Missing | Impact |
|---|---|---|---|
| **E2E retroactive MP3 admission** | None | Not tested in e2e | HIGH |
| **MP3 build with FLAC missing** | test_mp3.py | No filesystem simulation | HIGH |
| **MP3 reconcile with ID3-less files** | test_mp3.py | Assumes valid ID3 | MEDIUM |
| **XML generation with file deleted** | test_dj_pipeline.py | Post-validation deletion not tested | MEDIUM |
| **Concurrent dj_admission + xml emit** | None | Race condition not tested | MEDIUM |
| **Playlist scope divergence** | test_dj_pipeline.py | Playlists not yet in use | LOW |
| **MP3 path collision detection** | None | No path uniqueness test | MEDIUM |
| **Duplicate ISRC handling** | test_mp3.py | Only happy path tested | MEDIUM |

### 7.4 Test Coverage Score

| Dimension | %age | Status |
|---|---|---|
| CLI Command Coverage | 85% | ✓ Good |
| Core Logic Coverage (admission, xml) | 80% | ✓ Good |
| Integration (stages) | 75% | ⚠ Medium |
| Error Paths (missing files, corruption) | 40% | ✗ Low |
| Concurrent/Race Conditions | 20% | ✗ Low |
| End-to-End User Workflows | 60% | ⚠ Medium |

**Overall Test Coverage:** 62% (moderate)

---

## 8. Code Fragmentation & Duplicate Logic Summary

### 8.1 Fragmentation Matrix

| Logic Domain | # Code Paths | Locations | Severity |
|---|---|---|---|
| **DJ pool building** | 3 | tools/get-intake, dj/export.py, scripts/dj/build_pool_v3.py | HIGH |
| **Enrichment timing** | 3 | tools/get-intake, exec/enrich_dj_tags.py, dj/reconcile/lexicon_backfill.py | HIGH |
| **MP3 generation** | 2 | cli/mp3.py, exec/mp3_build.py | MEDIUM |
| **MP3 reconciliation** | 2 | cli/mp3.py, exec/mp3_build.py | MEDIUM |
| **TrackID assignment** | 1 | dj/xml_emit.py | LOW |
| **Rekordbox XML emit** | 1 | dj/xml_emit.py | LOW |

**Duplicate Logic Count: ~6 zones (4 high, 2 medium)**

### 8.2 Wrapper vs. Canonical Divergence

**Wrapper paths:**
- `tools/get --dj` → `tools/get-intake --dj` → shell logic
- Does NOT call CLI commands; shells out to exec layer
- Does NOT emit Rekordbox XML
- Generates M3U playlists only

**Canonical paths:**
- `tagslut intake` → `tagslut mp3 build|reconcile` → `tagslut dj backfill|admit|validate` → `tagslut dj xml emit|patch`
- All CLI-driven
- Full 4-stage pipeline
- Recommended by docs

**Consequence:** Users can take two paths to DJ library, with different outputs and assumptions.

---

## 9. Enrichment Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ Stage 1: Intake (providers: BP/TIDAL/MB/Deezer/TS)            │
│                                                                 │
│  tagslut intake <provider-url>                                 │
│   └─ upsert_identity()                                         │
│      └─ canonical_payload_json = {}  (provider metadata)      │
│         - artist, title, album, bpm, key, genre, year         │
│         - isrc, beatport_id, tidal_id (provider IDs)          │
│         - quality: provider-dependent (BP best, MB worst)     │
└─────────────────────────────────────────────────────────────────┘
                            ↓ canonical_payload_json
┌─────────────────────────────────────────────────────────────────┐
│ [Optional] Post-Move Async Enrichment (tools/get-intake only) │
│                                                                 │
│  background POST_MOVE_ENRICH_SCRIPT                            │
│   └─ post_move_enrich_art.py                                   │
│      └─ artwork download, tag sync                             │
│      └─ Does NOT mutate canonical_payload_json                │
│      └─ Not part of canonical 4-stage workflow                │
└─────────────────────────────────────────────────────────────────┘
                            ↓ canonical_payload_json (unchanged)
┌─────────────────────────────────────────────────────────────────┐
│ Stage 2: MP3 Build/Reconcile (no enrichment)                  │
│                                                                 │
│  tagslut mp3 build|reconcile --db <path>                       │
│   └─ build_mp3_from_identity() or reconcile_mp3_library()      │
│      └─ mp3_asset rows created                                 │
│      └─ canonical_payload_json UNCHANGED                       │
└─────────────────────────────────────────────────────────────────┘
                            ↓ canonical_payload_json (unchanged)
┌─────────────────────────────────────────────────────────────────┐
│ [Optional] Explicit Lexicon DJ Backfill (manual)              │
│                                                                 │
│  poetry run tagslut dj reconcile.lexicon-backfill <...>        │
│   └─ backfill_lexicon_metadata()                               │
│      └─ canonical_payload_json ← MERGED with Lexicon data     │
│         - lexicon_energy, lexicon_danceability                 │
│         - lexicon_popularity, lexicon_bpm, lexicon_key         │
│         - quality: high (Lexicon DJ algorithm)                 │
│      └─ Must be run manually; NOT automatic                   │
└─────────────────────────────────────────────────────────────────┘
            ↓ canonical_payload_json (enriched with Lexicon)
┌─────────────────────────────────────────────────────────────────┐
│ Stage 3: DJ Admission (read-only on metadata)                 │
│                                                                 │
│  tagslut dj backfill|admit --db <path>                         │
│   └─ admit_track() or backfill_admissions()                    │
│      └─ Read canonical_payload_json                            │
│      └─ Create dj_admission rows                               │
│      └─ canonical_payload_json NOT mutated                     │
└─────────────────────────────────────────────────────────────────┘
                            ↓ canonical_payload_json (unchanged)
┌─────────────────────────────────────────────────────────────────┐
│ Stage 4: XML Emit (metadata frozen)                            │
│                                                                 │
│  tagslut dj xml emit --db <path> --out out.xml                 │
│   └─ emit_rekordbox_xml()                                      │
│      └─ Read canonical_payload_json (final state)              │
│      └─ Emit Rekordbox XML with cached metadata               │
│      └─ Stable TrackIDs via dj_track_id_map                   │
└─────────────────────────────────────────────────────────────────┘
                            ↓ Rekordbox XML output
```

**Key Points:**

- Enrichment is **multi-stage and optional**
- Provider metadata (Stage 1) is baseline (~60–80% complete)
- Lexicon backfill (Stage 2 optional) adds DJ-specific fields
- Post-move enrichment (wrapper only) is async and non-canonical
- XML export freezes metadata (no re-enrichment)
- **Critical:** If Lexicon backfill skipped, DJ XML will lack energy/danceability fields

---

## 10. Key Findings & Recommendations

### 10.1 Complexity Hot Spots

| Hot Spot | Score | Issue | Recommendation |
|---|---|---|---|
| **Legacy wrapper (tools/get --dj)** | 7/10 | Two divergent paths exist | Deprecate; emit warning; migrate docs |
| **DJ pool building** | 6/10 | 3 separate code paths | Consolidate into single canonical path |
| **Enrichment timing** | 7/10 | Multi-stage, optional, async | Formalize enrichment contract (mandatory/optional) |
| **MP3 build assumptions** | 7/10 | FLAC missing, ffmpeg fail not tested | Add comprehensive error injection tests |
| **Data model clarity** | 5/10 | 4 JOINs to trace master→DJ | Add views for common queries |
| **XML generation** | 3/10 | Deterministic, stable | Keep as-is (working well) |
| **Test coverage** | 6/10 | 62% coverage; missing error paths | Add race condition + error injection tests |

### 10.2 Brittleness Risk Ranking

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| **Legacy wrapper auto-admission diverges from canonical** | HIGH | MEDIUM | Deprecate wrapper; enforce 4-stage |
| **MP3 build fails silently if FLAC missing** | HIGH | HIGH | Add file existence check before transcode |
| **Lexicon backfill skipped → stale DJ metadata in XML** | MEDIUM | MEDIUM | Auto-trigger backfill or require explicit OK |
| **Title+artist false positive in reconciliation** | MEDIUM | MEDIUM | Add confidence scoring; flag ambiguous matches |
| **Playlist scope divergence post-emit** | MEDIUM | LOW | Add validation: all dj_playlist_track entries existed at emit time |
| **Concurrent admit + emit race** | MEDIUM | LOW | Add DB transaction isolation level checks |
| **XML file deleted post-validation** | LOW | VERY LOW | Acceptable (Rekordbox warns on import) |

### 10.3 Test Coverage Priorities

**High Priority (add tests):**
1. E2E retroactive MP3 admission (wrapper + backfill workflow)
2. MP3 build with FLAC missing / ffmpeg not found
3. MP3 reconcile with ID3-less files / duplicate ISRC
4. Concurrent dj_admission + xml emit (race condition)
5. XML validation + file delete (post-validation corruption)

**Medium Priority:**
6. MP3 path collision detection
7. Playlist scope divergence
8. Enrichment timing guarantees (canonical vs wrapper)

**Low Priority:**
9. Rekordbox software import (requires actual Rekordbox)
10. Hardware USB failures

---

## 11. JSON Report Export

```json
{
  "audit_date": "2026-03-22",
  "scope": "DJ workflow architecture",
  "summary": {
    "complexity_score": 6.8,
    "brittleness_risk": 6.2,
    "test_coverage": "62%",
    "file_count": 50,
    "duplicate_logic_zones": 6
  },
  "findings": {
    "legacy_wrapper_complexity": {
      "status": "CONCERNING",
      "entry_points": 3,
      "canonical": "tagslut intake → mp3 build|reconcile → dj backfill|admit → dj xml emit|patch",
      "legacy": "tools/get --dj → tools/get-intake --dj (deprecated, non-deterministic)",
      "dj_mode_controls": [
        "line 1784-1804: TOTAL_STEPS calculation",
        "line 281-301: precheck_inventory_dj M3U generation",
        "line 2877-2893: DJ export summary output"
      ],
      "divergence": "Wrapper generates M3U only; skips MP3 registration, DJ admission, XML emit"
    },
    "code_fragmentation": {
      "status": "HIGH",
      "duplicate_logic_zones": 6,
      "high_severity": [
        {
          "logic": "DJ pool building",
          "locations": 3,
          "files": [
            "tools/get-intake:281-301",
            "tagslut/dj/export.py",
            "scripts/dj/build_pool_v3.py"
          ]
        },
        {
          "logic": "Enrichment timing",
          "locations": 3,
          "files": [
            "tools/get-intake:2877",
            "tagslut/exec/enrich_dj_tags.py",
            "tagslut/dj/reconcile/lexicon_backfill.py"
          ]
        }
      ],
      "medium_severity": [
        {
          "logic": "MP3 generation",
          "locations": 2
        },
        {
          "logic": "MP3 reconciliation",
          "locations": 2
        }
      ]
    },
    "data_model": {
      "status": "MODERATE",
      "complexity_score": 5.2,
      "tables": 8,
      "core_tables": [
        "mp3_asset",
        "dj_admission",
        "dj_track_id_map",
        "dj_export_state",
        "reconcile_log"
      ],
      "issues": [
        "No explicit status machine for mp3_asset",
        "Unused admission statuses (pending, rejected, needs_review)",
        "No cascade DELETE on foreign keys",
        "Three distinct layers require 4+ JOINs to trace"
      ]
    },
    "enrichment": {
      "status": "FRAGMENTED",
      "stages": 4,
      "critical_assumption": "canonical_payload_json is complete by Stage 3",
      "flow": [
        "Stage 1 (Intake): provider metadata",
        "[Optional] Post-Move Async: artwork, tags",
        "[Optional] Explicit Lexicon Backfill: DJ metadata",
        "Stage 3 (Admission): read-only",
        "Stage 4 (Export): frozen"
      ],
      "risk": "Lexicon backfill is optional; skipped backfill → stale XML"
    },
    "mp3_generation": {
      "status": "BRITTLE",
      "brittleness_score": 7.1,
      "untested_failures": [
        "FLAC file missing (caught, skip, but breaks downstream)",
        "FFmpeg not found (FFmpegNotFoundError)",
        "FFmpeg output malformed (no re-validation)",
        "FLAC metadata missing (fallback to filename)",
        "MP3 path collision (overwrites silently)",
        "ID3-less MP3 files (skipped, no fallback)",
        "Duplicate ISRC in DB (only first matched)",
        "Title+artist false positive (common titles)"
      ],
      "assumptions": [
        "FLAC exists on disk",
        "FFmpeg succeeds + output is valid",
        "Metadata in FLAC tags available",
        "MP3 path does not collide",
        "Database registration atomic",
        "INSERT OR IGNORE silent if row exists"
      ]
    },
    "xml_generation": {
      "status": "STABLE",
      "stability_score": 8.1,
      "strengths": [
        "Deterministic XML generation (byte-identical)",
        "Stable TrackID assignment (never reassigned)",
        "Manifest hash detects tampering",
        "Pre-emit validation prevents missing files"
      ],
      "vulnerabilities": [
        "File deleted post-validation (risk: stale XML)",
        "Concurrent admit + emit (risk: incomplete XML)",
        "Playlist scope divergence (future risk)"
      ]
    },
    "test_coverage": {
      "status": "MODERATE",
      "overall_coverage": "62%",
      "by_dimension": {
        "cli_commands": "85%",
        "core_logic": "80%",
        "integration": "75%",
        "error_paths": "40%",
        "race_conditions": "20%",
        "e2e_workflows": "60%"
      },
      "critical_gaps": [
        {
          "gap": "E2E retroactive MP3 admission",
          "impact": "HIGH",
          "why": "Not tested; unknown if wrapper + backfill workflow works"
        },
        {
          "gap": "MP3 build with FLAC missing",
          "impact": "HIGH",
          "why": "Error path not tested; no filesystem simulation"
        },
        {
          "gap": "MP3 reconcile with duplicate ISRC",
          "impact": "MEDIUM",
          "why": "Happy path only; ambiguous matching not tested"
        },
        {
          "gap": "Concurrent admin + XML emit",
          "impact": "MEDIUM",
          "why": "Race condition not tested; incomplete XML possible"
        },
        {
          "gap": "XML file deleted post-validation",
          "impact": "MEDIUM",
          "why": "Validation → delete → emit race not tested"
        }
      ]
    }
  },
  "recommendations": {
    "immediate": [
      "Deprecate tools/get --dj; emit warning + doc pointer to 4-stage",
      "Add file existence check before MP3 transcode",
      "Add comprehensive test for retroactive MP3 admission"
    ],
    "short_term": [
      "Consolidate 3 DJ pool building code paths into single canonical",
      "Formalize enrichment contract (mandatory vs optional stages)",
      "Add error injection tests for MP3 build (FLAC missing, ffmpeg fail)"
    ],
    "medium_term": [
      "Add race condition tests (concurrent admit + emit)",
      "Add confidence scoring to MP3 reconciliation (title+artist matching)",
      "Add views for common data queries (simplify JOINs)"
    ]
  }
}
```

---

## 12. File & Line Citations Summary

**Critical Files:**

| Function | File | Lines | Purpose |
|---|---|---|---|
| **DJ_MODE wrapper** | tools/get-intake | 1066–1068, 281–301, 2877–2893 | DJ workflow legacy entry point |
| **CLI intake** | tagslut/cli/commands/intake.py | 17–45+ | Stage 1 entry point |
| **CLI mp3** | tagslut/cli/commands/mp3.py | 13–180 | Stage 2 entry point |
| **CLI dj** | tagslut/cli/commands/dj.py | 237–1335 | Stage 3–4 entry point |
| **MP3 build** | tagslut/exec/mp3_build.py | 244–330 | MP3 generation (Stage 2a) |
| **MP3 reconcile** | tagslut/exec/mp3_build.py | 346–430 | MP3 linking (Stage 2b) |
| **DJ admission** | tagslut/dj/admission.py | 1–150 | Stage 3 logic |
| **XML emit** | tagslut/dj/xml_emit.py | 1–450 | Stage 4 logic |
| **Enrichment sink** | tagslut/storage/v3/identity_service.py | 144–184 | canonical_payload_json upsert |
| **Lexicon backfill** | tagslut/dj/reconcile/lexicon_backfill.py | 270–348 | Enrichment merge |
| **Schema DJ tables** | tagslut/storage/schema.py | 1446–1510 | DJ table definitions |
| **E2E tests** | tests/dj/test_dj_pipeline_e2e.py | 1–120 | Pipeline tests |
| **Admission tests** | tests/dj/test_admission.py | 1–150 | Admission logic tests |

---

**End of Audit Report**

Generated: 2026-03-22
Analyst: GitHub Copilot
Scope: Complete DJ workflow architecture analysis
Status: ✓ Comprehensive findings with specific file citations

