# Roon Integration Analysis

## Summary

Your Roon export (`roon.xlsx`) contains **11,502 tracks** with high-quality curated metadata from MusicBrainz and AllMusic (Rovi). This is a goldmine for validation and enhancement!

## Key Findings

### Database Reconciliation
- **11,501 tracks matched** between Roon and database (99.99% match!)
- **1 track** in Roon but not in DB (likely moved/renamed)
- **11,958 files** in DB but not Roon (these are suspect/quarantine zones, recoveries, etc.)

### Metadata Richness
- **5,398 MusicBrainz IDs** available (47% of Roon library)
- **3,296 Rovi/AllMusic IDs** available (29% of Roon library)
- **93 files** can be enhanced with MusicBrainz IDs from Roon

### Duplicate Detection
- **0 duplicates** detected by Roon (all marked "Is Dup?: no")
- This is interesting - Roon likely already de-duplicated your library
- Our system found 8,174 duplicate hash groups - these are likely files Roon doesn't see (suspect/quarantine/recovery zones)

## What Makes Roon Data Valuable

### 1. **Authoritative MusicBrainz IDs**
Roon's metadata engine combines:
- MusicBrainz (open music encyclopedia)
- AllMusic/Rovi (professional music database)
- Their own algorithms and curation

**Example MusicBrainz IDs from your export:**
```
mb:183559821418873  - !!! - Myth Takes - Track 01
mb:183559821418874  - !!! - All My Heroes Are Weirdos
rovi:MT0004597333   - !!! - Get Up
```

### 2. **Duration Data** (if available in Roon)
While not in this export, Roon tracks duration internally. MusicBrainz IDs allow you to:
- Query MusicBrainz API for official track lengths
- Validate against actual file durations
- Detect stitched R-Studio recoveries

### 3. **Composer Information**
Your export includes detailed composer credits:
```
Eve / Nate Dogg / DJ Quik
Nic Offer / Dan Gorman / Justin Van Der Volgen / Mario Andreoni / ...
```

This is valuable for classical music and jazz where composer matters more than artist.

### 4. **Album Artist Normalization**
Roon has already normalized artist names for you (e.g., "!!!" instead of variations).

## Integration Strategies

### Strategy 1: Enhance Database with MusicBrainz IDs ✅ READY

Add MusicBrainz track IDs to your 93 files missing them:

```bash
# Dry-run (see what would change)
python tools/integrity/import_roon.py \
  --roon-export roon.xlsx \
  --update-musicbrainz \
  -v

# Execute updates
python tools/integrity/import_roon.py \
  --roon-export roon.xlsx \
  --update-musicbrainz \
  --execute \
  -v
```

**Benefits:**
- Files will have proper `musicbrainz_trackid` tag
- Can query MusicBrainz API for official durations
- Better duplicate detection via MusicBrainz fingerprinting

### Strategy 2: Duration Validation via MusicBrainz API

Create tool to:
1. Extract MusicBrainz IDs from Roon data
2. Query MusicBrainz API for official track lengths
3. Update files with `MUSICBRAINZ_TRACK_LENGTH` tag
4. Run duration validator to find stitched files

**Example workflow:**
```bash
# Step 1: Import MusicBrainz IDs from Roon
python tools/integrity/import_roon.py \
  --roon-export roon.xlsx \
  --update-musicbrainz \
  --execute

# Step 2: Query MusicBrainz API for durations (NEW TOOL)
python tools/integrity/fetch_musicbrainz_durations.py \
  --update-tags

# Step 3: Validate durations
python tools/integrity/validate_durations.py \
  --zone suspect \
  -o stitched_report.json
```

### Strategy 3: Cross-Reference Duplicate Detection

Compare our duplicate detection (8,174 groups) with Roon's clean library (0 duplicates):

```sql
-- Files in our duplicates but in Roon's library
SELECT f.path, f.zone, r.title, r.album
FROM files f
JOIN roon_tracks r ON f.path = r.path
WHERE f.sha256 IN (
  SELECT sha256 FROM files GROUP BY sha256 HAVING COUNT(*) > 1
);
```

**This reveals:**
- Files Roon considers "good" but we flagged as duplicates
- Potential false positives in our detection
- Different encodings of same track Roon merged

### Strategy 4: Identify Files to Re-acquire

Files in Roon but not in database (1 file):
- Likely moved, renamed, or deleted
- Roon still has metadata even if file missing
- Can generate "re-acquire" list

```bash
python tools/integrity/import_roon.py \
  --roon-export roon.xlsx \
  --db music.db \
  -o roon_analysis.json

# Check missing_in_db section
cat roon_analysis.json | jq '.missing_in_db'
```

### Strategy 5: Update Tags in Files

Use Roon's normalized metadata to fix tags:

```python
# Pseudo-code for batch tagging
for roon_track in roon_tracks:
    if roon_track.musicbrainz_id:
        flac_file = FLAC(roon_track.path)
        flac_file['MUSICBRAINZ_TRACKID'] = roon_track.musicbrainz_id
        flac_file['ALBUM_ARTIST'] = roon_track.album_artist  # Normalized
        flac_file['COMPOSER'] = roon_track.composers
        flac_file.save()
```

## Recommended Workflow

### Phase 1: Import MusicBrainz IDs (Immediate)

```bash
# 1. Backup database
cp music.db music.db.backup

# 2. Import MusicBrainz IDs
python tools/integrity/import_roon.py \
  --roon-export roon.xlsx \
  --db music.db \
  --update-musicbrainz \
  --execute \
  -v

# Result: 93 files enhanced with MusicBrainz track IDs
```

### Phase 2: Fetch Durations from MusicBrainz API (Next)

Create new tool to:
- Query musicbrainz.org API for track durations
- Update metadata_json with `musicbrainz_track_length`
- Rate-limit API calls (1 request/second, MusicBrainz requirement)

```bash
# NEW TOOL (to be created)
python tools/integrity/fetch_musicbrainz_durations.py \
  --db music.db \
  --limit 1000 \
  -v
```

### Phase 3: Comprehensive Validation (After API fetch)

```bash
# Run duration validator with MusicBrainz data
python tools/integrity/validate_durations.py \
  --db music.db \
  --zone suspect \
  --strict \
  -o stitched_files_report.json
```

### Phase 4: Reconcile Duplicates (Later)

Cross-check our duplicates with Roon's de-duplicated library to find false positives.

## Technical Implementation Notes

### MusicBrainz API Integration

**Endpoint:**
```
https://musicbrainz.org/ws/2/recording/{mbid}?fmt=json
```

**Example Response:**
```json
{
  "id": "183559821418873",
  "title": "Myth Takes",
  "length": 215300,  // milliseconds
  "artist-credit": [...],
  "releases": [...]
}
```

**Rate Limits:**
- 1 request per second
- Polite user-agent required: "YourApp/1.0 (email@example.com)"

### Database Schema Update

Add MusicBrainz duration to metadata:

```python
# In metadata_json
{
  "musicbrainz_trackid": "183559821418873",
  "musicbrainz_track_length": "215300",  // milliseconds
  "title": "Myth Takes",
  "album": "Myth Takes"
}
```

Duration validator already checks for this tag!

### Roon Export Refresh

Roon allows periodic exports:
1. Roon → Settings → General → Export Library
2. Choose "Export Library to Excel"
3. Includes all tracked metadata

**Recommended frequency:** Monthly or after major library changes

## Files Created

1. **`tools/integrity/import_roon.py`** - Roon import and reconciliation tool
2. **`examine_roon.py`** - Quick spreadsheet examiner (can be deleted)

## Next Steps

### Immediate (Ready to Run)

```bash
# Import MusicBrainz IDs from Roon
python tools/integrity/import_roon.py \
  --roon-export roon.xlsx \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_20260119/music.db \
  --update-musicbrainz \
  --execute \
  -v

### Future Tools to Create

1. **`tools/integrity/fetch_musicbrainz_durations.py`**
   - Query MusicBrainz API for track lengths
   - Add `musicbrainz_track_length` to metadata
   - Rate-limited (1 req/sec)

2. **`tools/integrity/compare_roon_duplicates.py`**
   - Cross-check our duplicates with Roon's library
   - Find false positives
   - Generate reconciliation report

3. **`tools/integrity/sync_roon_tags.py`**
   - Update FLAC tags with Roon's normalized metadata
   - Composer, album artist, etc.
   - Batch tagging with progress bar

## Summary Stats from Your Roon Library

```
Total Tracks:           11,502
MusicBrainz Coverage:    5,398 (47%)
Rovi/AllMusic Coverage:  3,296 (29%)
Duplicates (Roon):           0 (already de-duped)
Match Rate with DB:     11,501 (99.99%)
Can Enhance:                93 files
```

Your Roon library is extremely clean and well-curated! The integration will significantly enhance duration validation and metadata quality.
