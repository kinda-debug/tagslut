# Download Strategy: TIDAL-First with Beatport Enrichment

## Core Philosophy

**TIDAL is the primary audio source. Beatport is the metadata authority for DJ tags.**

## Workflow

### 1. User provides Beatport URL
```
https://www.beatport.com/track/example/12345
```

### 2. Extract ISRC from Beatport
```python
# Via Beatport API (using beatportdl token)
beatport_track = beatport_api.get_track(12345)
isrc = beatport_track['isrc']  # e.g., 'USRC17607839'
```

### 3. Download from TIDAL using ISRC
```bash
# Use tiddl to download by ISRC match
tiddl --isrc USRC17607839 --output $ROOT_TD
```

### 4. Enrich with Beatport metadata
```python
# Apply Beatport DJ tags to TIDAL download
tidal_file = f"{ROOT_TD}/downloaded_track.flac"
apply_beatport_metadata(tidal_file, beatport_track)
```

## Why TIDAL First?

1. **Audio Quality**: TIDAL provides lossless FLAC at competitive quality
2. **Availability**: Broader catalog than Beatport's download service
3. **Licensing**: Better terms for personal library use
4. **Consistency**: Single audio source = consistent quality baseline

## Why Beatport for Metadata?

1. **DJ-Specific Tags**: BPM, key, genre, energy level
2. **Catalog Numbers**: Essential for library organization
3. **Release Context**: Label, release date, original mix vs remix
4. **Standardization**: Beatport's genre/tag taxonomy is DJ-industry standard

## Tool Roles

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **tiddl** | Download audio from TIDAL | Always (primary download) |
| **beatportdl** | Token provider for Beatport API | Never for downloads, only for metadata API access |
| **Beatport API** | Fetch track metadata, ISRC lookups | Enrichment phase after download |
| **tagslut** | Orchestrate workflow, manage DB | All phases |

## Edge Cases

### Beatport link but no TIDAL match
```
1. Attempt ISRC match on TIDAL
2. If no match: flag for manual review
3. Do NOT fall back to Beatport download automatically
4. User decides: wait for TIDAL availability or manual exception
```

### TIDAL link (not Beatport)
```
1. Download from TIDAL directly
2. Attempt Beatport metadata enrichment via ISRC reverse lookup
3. If no Beatport match: proceed with TIDAL metadata only
```

### Both sources have different ISRCs (conflict)
```
1. Trust TIDAL ISRC (it's the audio source)
2. Log Beatport ISRC discrepancy
3. Store both in canonical_payload_json.provider_id_conflicts
4. Flag for manual review
```

## Configuration
```bash
# env_exports.sh priorities
PRIMARY_SOURCE="tidal"           # Never change
METADATA_AUTHORITY="beatport"    # For DJ tags only
FALLBACK_ENABLED=false           # No automatic fallback to Beatport downloads
```

## Migration Note

If you have existing Beatport downloads from `beatportdl`:
- They stay in `/Volumes/MUSIC/mdl/bpdl` (read-only reference)
- New acquisitions: TIDAL downloads → `/Volumes/MUSIC/mdl/tidal`
- Deduplication: ISRC-based, prefer TIDAL source
