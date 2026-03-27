# Backfill Implementation Guide

## Core Principle

When a track is identified (by ISRC, title+artist, or fingerprint), **check if it already exists in the library FIRST**. If it does:
- Don't re-download
- Extract metadata from existing file
- Enrich with data from metadata services
- Return the path

This is the opposite of "skip if exists" — it's "process existing files more thoroughly."

---

## Backfill Methods (in Priority Order)

### 1. Query DB by ISRC (Fastest)

```python
async def find_by_isrc(self, isrc: str) -> Optional[Path]:
    """
    Query track_identity table for matching ISRC.
    Returns path if found.
    """
    if not self.db_path:
        return None
    
    # Pseudocode; adapt to your ORM
    result = db.session.query(TrackIdentity).filter(
        TrackIdentity.isrc == isrc
    ).first()
    
    if result:
        return Path(result.path)
    return None
```

**Outcome:** If found, path is known. Set `result=FOUND_IN_LIBRARY`, skip to enrichment.

---

### 2. Query DB by Provider ID (Fast)

```python
async def find_by_provider_id(
    self, 
    tidal_id: Optional[str] = None,
    beatport_id: Optional[str] = None,
    qobuz_id: Optional[str] = None,
) -> Optional[Path]:
    """
    Query track_identity by provider IDs.
    Returns path if all matching IDs agree on same ISRC.
    """
    matches = []
    
    if tidal_id:
        result = db.session.query(TrackIdentity).filter(
            TrackIdentity.tidal_id == tidal_id
        ).first()
        if result:
            matches.append(result)
    
    if beatport_id:
        result = db.session.query(TrackIdentity).filter(
            TrackIdentity.beatport_id == beatport_id
        ).first()
        if result:
            matches.append(result)
    
    if qobuz_id:
        result = db.session.query(TrackIdentity).filter(
            TrackIdentity.qobuz_id == qobuz_id
        ).first()
        if result:
            matches.append(result)
    
    if not matches:
        return None
    
    # Verify all matches agree on ISRC (no conflicts)
    isrcs = {m.isrc for m in matches}
    if len(isrcs) > 1:
        # Conflict: log and flag as uncertain
        # Don't auto-resolve, return None
        logger.warning(f"ISRC conflict for provider IDs: {isrcs}")
        return None
    
    # All agree: return first match's path
    return Path(matches[0].path)
```

**Outcome:** If all provider IDs agree on same ISRC, path is known. Otherwise, skip to fuzzy match.

---

### 3. Fuzzy Match on Title+Artist (Slow)

```python
async def find_by_fuzzy_match(
    self,
    title: str,
    artist: str,
    threshold: float = 0.85
) -> Optional[Tuple[Path, float]]:
    """
    Fuzzy match by title+artist against library.
    Returns (path, score) if score > threshold, else None.
    """
    from rapidfuzz import fuzz
    
    # Query all tracks in library (or use pre-built index)
    all_tracks = db.session.query(TrackIdentity).all()
    
    best_match = None
    best_score = 0
    
    for track in all_tracks:
        # Score: average of title and artist similarity
        title_score = fuzz.token_set_ratio(title.lower(), track.title.lower())
        artist_score = fuzz.token_set_ratio(artist.lower(), track.artist.lower())
        avg_score = (title_score + artist_score) / 2.0
        
        if avg_score > best_score:
            best_score = avg_score
            best_match = track
    
    if best_match and best_score > threshold:
        return Path(best_match.path), best_score
    
    return None
```

**Outcome:** If score > 0.85, likely match. If 0.70–0.85, uncertain (flag for review).

---

### 4. Fingerprint Match (Advanced)

```python
async def find_by_fingerprint(
    self,
    audio_path: Path,
    threshold: float = 0.90
) -> Optional[Tuple[Path, float]]:
    """
    Match by audio fingerprint (Chromaprint/AcoustID).
    Requires audio file already downloaded.
    """
    # Pseudocode; requires acoustid library
    fingerprint = chromaprint.fingerprint(str(audio_path))
    
    # Query AcoustID API
    result = acoustid.search(fingerprint)
    
    if result and result.score > threshold:
        # Look up recording in DB
        recording_id = result.recording_id
        track = db.session.query(TrackIdentity).filter(
            TrackIdentity.acoustid_id == recording_id
        ).first()
        
        if track:
            return Path(track.path), result.score
    
    return None
```

**Outcome:** High-confidence match if score > 0.90. Useful for resolving ambiguous fuzzy matches.

---

## Backfill Pipeline Integration

```python
async def backfill_single_track(self, track: TrackResult) -> None:
    """
    Main backfill logic for one track.
    Tries methods in order until match found.
    """
    
    # Method 1: ISRC lookup
    if track.isrc:
        path = await self.find_by_isrc(track.isrc)
        if path:
            track.path = str(path)
            track.result = ProcessingResult.FOUND_IN_LIBRARY
            logger.info(f"Backfill: Found by ISRC: {path}")
            return
    
    # Method 2: Provider ID lookup
    path = await self.find_by_provider_id(
        tidal_id=track.metadata.get('tidal_id'),
        beatport_id=track.metadata.get('beatport_id'),
        qobuz_id=track.metadata.get('qobuz_id'),
    )
    if path:
        track.path = str(path)
        track.result = ProcessingResult.FOUND_IN_LIBRARY
        logger.info(f"Backfill: Found by provider ID: {path}")
        return
    
    # Method 3: Fuzzy match
    match_result = await self.find_by_fuzzy_match(track.title, track.artist)
    if match_result:
        path, score = match_result
        if score > 0.90:
            # High confidence: accept
            track.path = str(path)
            track.result = ProcessingResult.FOUND_IN_LIBRARY
            logger.info(f"Backfill: Fuzzy match (score={score}): {path}")
            return
        elif score > 0.70:
            # Uncertain: flag for review
            track.result = ProcessingResult.SKIPPED
            track.error = f"Fuzzy match uncertain (score={score})"
            logger.warning(f"Backfill: Uncertain match (score={score}): {path}")
            return
    
    # No match found
    track.result = ProcessingResult.SKIPPED
    track.error = "Not found in library"
    logger.info(f"Backfill: Not found: {track.artist} - {track.title}")


async def backfill_library(self) -> None:
    """Backfill all tracks in self.results"""
    console.print("[cyan]→ Backfilling library...[/cyan]")
    
    for i, track in enumerate(self.results, 1):
        await self.backfill_single_track(track)
        if track.path:
            console.print(f"  [{i}/{len(self.results)}] ✓ {track.artist} - {track.title}")
        else:
            console.print(f"  [{i}/{len(self.results)}] ⚠ Missing: {track.artist} - {track.title}")
```

---

## Enrichment After Backfill

Once a file is found (backfilled or downloaded), enrich its metadata:

```python
async def enrich_track(self, track: TrackResult) -> None:
    """
    Enrich track with metadata from services.
    Runs after backfill (whether file was found or downloaded).
    """
    if not track.path or not Path(track.path).exists():
        return
    
    # Method 1: Query DB (fastest)
    db_record = db.session.query(TrackIdentity).filter(
        TrackIdentity.path == track.path
    ).first()
    
    if db_record:
        # Merge DB data
        track.isrc = track.isrc or db_record.isrc
        track.duration_ms = track.duration_ms or db_record.duration_ms
        track.metadata_sources.append('db')
        logger.info(f"Enriched from DB: {track.path}")
        return
    
    # Method 2: Extract from FLAC tags
    try:
        from mutagen.flac import FLAC
        audio = FLAC(track.path)
        
        if audio.info:
            track.duration_ms = int(audio.info.length * 1000)
        
        # Extract tags
        if 'ISRC' in audio:
            track.isrc = audio['ISRC'][0]
        
        track.metadata_sources.append('flac_tags')
        logger.info(f"Enriched from FLAC tags: {track.path}")
    except Exception as e:
        logger.warning(f"Failed to extract FLAC tags: {track.path}: {e}")
    
    # Method 3: Query metadata services (only if missing data)
    if not track.duration_ms or not track.isrc:
        # Query Beatport, Tidal, Qobuz...
        # Store results with provenance
        pass


async def backfill_all(self) -> None:
    """Backfill + enrich all tracks"""
    await self.backfill_library()  # Find in library
    
    # Enrich all (whether found or not)
    for track in self.results:
        await self.enrich_track(track)
```

---

## Database Schema (Assumed)

```python
class TrackIdentity(Base):
    __tablename__ = 'track_identity'
    
    id = Column(Integer, primary_key=True)
    path = Column(String, unique=True, nullable=False)
    
    # Identifiers
    isrc = Column(String)
    tidal_id = Column(String)
    beatport_id = Column(String)
    qobuz_id = Column(String)
    acoustid_id = Column(String)
    musicbrainz_id = Column(String)
    
    # Metadata
    title = Column(String)
    artist = Column(String)
    album = Column(String)
    duration_ms = Column(Integer)
    
    # Provenance
    ingested_at = Column(DateTime, default=datetime.utcnow)
    ingestion_method = Column(String)  # 'provider_api', 'local_tags', etc.
    ingestion_confidence = Column(String)  # 'verified', 'high', 'uncertain', 'legacy'
```

---

## Key Principles

1. **Try fastest methods first** (ISRC → provider ID → fuzzy → fingerprint)
2. **Stop as soon as confident match found** (don't over-search)
3. **Flag conflicts, don't auto-resolve** (ISRC mismatch = uncertain)
4. **Always enrich** (even found files get metadata harvested)
5. **Log everything** (debug trail for troubleshooting)
6. **No re-downloads** (if file exists, use it)
7. **Backfill doesn't block** (missing files don't stop pipeline)

---

## Testing Checklist

- [ ] ISRC lookup works (DB populated)
- [ ] Provider ID lookup works (handles conflicts)
- [ ] Fuzzy match works (score calculation correct)
- [ ] Fingerprint lookup works (AcoustID API accessible)
- [ ] Enrichment populates metadata (FLAC tags, DB, API)
- [ ] No re-downloads (existing files used as-is)
- [ ] Missing files don't block (pipeline continues)
- [ ] Conflicts are flagged (not silently resolved)
- [ ] Provenance is recorded (ingestion_method, confidence)
