# tools/get-intake Refactor: Useful Output, Backfill, Unified Input

## Problem Statement

**Current state:** `tools/get-intake` produces 200+ lines of formatted output (newspaper style) that:
- Hides actual file paths in tables
- Shows status descriptions instead of actionable results
- Blocks downstream operations if files already exist
- Requires separate handling for URLs, playlists, and local directories

**Impact:** Unusable for scripting, debugging, or quick lookups. Verbose but useless.

---

## Design Goals

1. **Useful verbosity:** Show file paths and outcomes, not meta-narrative
2. **Backfill existing files:** If a track exists in library, enrich its metadata without re-download
3. **Unblock downstream:** `--dj` works even if all files exist; returns playlist regardless
4. **Unified input:** URLs, playlists, directories → single pipeline
5. **Structured output:** JSON, M3U, CSV for downstream consumption

---

## Architecture

### Input Type Detection

```
Source
├─ URL (tidal/beatport/qobuz)
│  └─ Extract track ID → Query API → Harvest metadata → Match to library
├─ Playlist file (M3U/JSON/CSV)
│  └─ Parse tracks → Match to library by ISRC/title+artist
├─ Local directory
│  └─ Scan audio files → Extract tags → Process like remote source
└─ (New) --scan flag
   └─ Treat any input as local directory, process uniformly
```

### Processing Pipeline

**Phase 1: Ingest**
- Detect input type
- Extract track metadata (title, artist, ISRC, duration, etc.)
- Build list of `TrackResult` objects

**Phase 2: Backfill (NEW)**
- For each track, check if already in library
  - By ISRC (DB lookup)
  - By title+artist (fuzzy match)
  - By fingerprint (if available)
- If found: set `path`, update `result=FOUND_IN_LIBRARY`, skip download
- If not found: proceed to download (if `--force-download`)

**Phase 3: Enrich**
- Query metadata services (Beatport, Tidal, Qobuz) for missing data
- Harvest tags, durations, genres, etc.
- Store in DB with provenance

**Phase 4: Output**
- Format results (summary, JSON, M3U, CSV)
- Write to console or file
- Return exit code (0 = success, 1 = error)

---

## Output Format

### Summary (Default, Human-Readable)

```
━━━ INTAKE SUMMARY ━━━
Total tracks: 42
  found: 38
  backfilled: 4
  downloaded: 0
  enriched: 38
  failed: 0

✓ FOUND (38):
  Deadmau5 - Some Chords
    → /Volumes/MUSIC/MASTER_LIBRARY/Electronic/Deadmau5/.../file.flac
  Justice - D.A.N.C.E.
    → /Volumes/MUSIC/MASTER_LIBRARY/Electronic/Justice/.../file.flac
  ... and 36 more

⚠ MISSING (4):
  Unknown Artist - Unknown Title
  Rare Track - Obscure Label
  ... and 2 more
```

**Key changes:**
- Paths first (not buried in tables)
- Outcome types clear (found, backfilled, missing, failed)
- One track per line (scannable)
- "and N more" for length control

### JSON (Machine-Readable)

```json
{
  "timestamp": "2026-03-27T12:34:56.789Z",
  "summary": {
    "total": 42,
    "found": 38,
    "backfilled": 4,
    "missing": 4
  },
  "tracks": [
    {
      "identifier": "USRC1234567890",
      "title": "Some Chords",
      "artist": "Deadmau5",
      "album": "Album Name",
      "path": "/Volumes/MUSIC/MASTER_LIBRARY/.../file.flac",
      "source": "tidal",
      "result": "backfilled",
      "metadata_sources": ["tidal", "beatport"],
      "duration_ms": 240000,
      "isrc": "USRC1234567890"
    },
    ...
  ]
}
```

### M3U (Playlist Export)

```
#EXTM3U
#EXTINF:240,Deadmau5 - Some Chords
/Volumes/MUSIC/MASTER_LIBRARY/.../file.flac
#EXTINF:195,Justice - D.A.N.C.E.
/Volumes/MUSIC/MASTER_LIBRARY/.../file.flac
```

### CSV (Tabular Export)

```
identifier,artist,title,album,path,source,result,isrc
USRC1234567890,Deadmau5,Some Chords,Album Name,/Volumes/.../file.flac,tidal,backfilled,USRC1234567890
...
```

---

## Command Examples

### Process Tidal Track (Backfill if Exists)

```bash
tools/get-intake https://tidal.com/track/439819932/u

# Output:
# ━━━ INTAKE SUMMARY ━━━
# Total tracks: 1
#   found: 1
# ✓ FOUND (1):
#   Sabrina Carpenter - Manchild
#     → /Volumes/MUSIC/MASTER_LIBRARY/Pop/Sabrina Carpenter/Short n Sweet/Manchild.flac
```

### Process Tidal Track + DJ Pipeline (Even if Exists)

```bash
tools/get-intake https://tidal.com/track/439819932/u --dj

# Outputs:
# - Console summary (as above)
# - M3U playlist: LIB:playlists/roon-tidal-20260327-004552.m3u (with existing files)
# - DJ pipeline runs (no re-download if file exists)
```

### Return as Playlist File (--re flag)

```bash
tools/get-intake https://tidal.com/track/439819932/u --re

# Outputs:
# - Console summary (as above)
# - M3U playlist file: track_20260327_004552.m3u (auto-named by source + timestamp)
# - File saved in current directory (or use --output-file to specify path)
```

```bash
tools/get-intake ~/Downloads/Workout.m3u --re

# Auto-names: Workout_20260327_004552.m3u
# Returns matched tracks with correct library paths
```

```bash
tools/get-intake /Volumes/MUSIC/mdl/tidal --scan --re

# Auto-names: tidal_20260327_004552.m3u
# Scans directory, matches to library, exports as playlist
```

### Return Playlist + Custom Filename

```bash
tools/get-intake https://tidal.com/track/439819932/u --re --output-file ~/Music/Playlists/MyPlaylist.m3u

# Saves to specified path instead of auto-naming
```

### Process Playlist File

```bash
tools/get-intake ~/Downloads/Workout.m3u

# Output:
# ━━━ INTAKE SUMMARY ━━━
# Total tracks: 24
#   found: 22
#   missing: 2
# ✓ FOUND (22):
#   ... (paths)
# ⚠ MISSING (2):
#   Obscure Remix - Unknown Artist
#   Rare Track - Deleted Label
```

### Scan Local Directory (Like Remote Source)

```bash
tools/get-intake /Volumes/MUSIC/mdl/tidal --scan

# Scans all FLAC/MP3 files in directory
# Extracts metadata from tags
# Enriches from DB / metadata services
# Returns JSON/M3U/CSV

# Output:
# → Scanning local directory: /Volumes/MUSIC/mdl/tidal
# ✓ Found 33 audio file(s)
# → Backfilling library metadata...
#   ✓ Already in library: 24 files
#   ⚠ New files: 9 files
# ━━━ INTAKE SUMMARY ━━━
# ... (as above)
```

### Export as JSON

```bash
tools/get-intake https://tidal.com/track/439819932/u --output json --output-file track.json

# Generates track.json with full metadata
```

### Export as M3U (Playlist)

```bash
tools/get-intake ~/Downloads/Playlist.csv --output m3u --output-file fixed.m3u

# Generates fixed.m3u with correct paths to library files
```

---

## Integration with Existing Systems

### Backfill Algorithm

When a track is identified (by ISRC, tidal_id, beatport_id, or title+artist):

1. **Query DB by ISRC** (fastest)
   - If found: Use existing `track_identity.path`
   - Return immediately

2. **Query DB by provider ID** (tidal_id, beatport_id, etc.)
   - If found and ISRCs match: Use existing path
   - If found but ISRC conflicts: Flag in results, use with caution

3. **Fuzzy match on title+artist** (slowest)
   - Score candidates using Levenshtein/Jaro
   - If score > 0.85: Consider as match
   - Manual confirmation if uncertain

### Metadata Harvesting

For tracks without complete metadata:
- Query Tidal API (if available)
- Query Beatport API (if available)
- Query Qobuz API (if available)
- Store results with provenance (source, timestamp, confidence)

### DJ Pipeline Integration

If `--dj` flag is set:
1. Generate M3U playlist (even if all files exist)
2. Check files against DJ library requirements
3. Admit qualifying tracks to DJ pool
4. Return admission status in output

**Key:** Does not block if files already exist. Processes and returns playlist regardless.

---

## Backward Compatibility

**Current users of `tools/get-intake`:**
- Codex (automated intake)
- Manual intake runs
- Scripts that parse output

**Compatibility plan:**
1. Add `--output` flag (default: `summary` for backward compat)
2. If existing scripts parse the newspaper format, they'll need update
3. **Recommendation:** Migrate to JSON output for robustness

---

## Implementation Checklist

- [ ] Refactor input detection (URL/playlist/directory)
- [ ] Implement backfill logic (DB lookup, fuzzy match, fingerprint)
- [ ] Rewrite console output (summary format)
- [ ] Add JSON export
- [ ] Add M3U export
- [ ] Add CSV export
- [ ] Integrate with DJ pipeline (--dj flag)
- [ ] Add --scan flag (local directory processing)
- [ ] Test with existing workflows (Codex, manual runs)
- [ ] Update documentation (CLI help, examples)
- [ ] Update tests (new output format, backfill logic)

---

## File Locations to Update

```
tools/get-intake                          # Main entry point (bash wrapper)
tagslut/exec/get_intake_console.py        # Console output formatter (REWRITE)
tagslut/exec/get_intake_pipeline.py       # Core pipeline (UPDATE)
tagslut/database/track_identity.py        # DB queries (ADD backfill methods)
tests/e2e/test_intake.py                  # E2E tests (UPDATE)
docs/INTAKE_GUIDE.md                      # User documentation (UPDATE)
docs/CLI_REFERENCE.md                     # CLI reference (UPDATE)
```

---

## Exit Codes

- `0`: Success (tracks found/processed)
- `1`: Error (no tracks found, API failure, DB error)
- `2`: Partial failure (some tracks failed, others succeeded)

---

## Flags Reference

### Input/Processing
- `--scan`: Treat input as local directory, process like remote source
- `--backfill`: Extract metadata from existing library files (default: enabled)
- `--dj`: Run DJ pipeline (works even if all files exist, returns playlist)
- `--force-download`: Force re-download even if file exists (overrides backfill)

### Output
- `--re` or `--return`: Save results as M3U playlist file (auto-named by source + timestamp)
- `--output {summary|json|m3u|csv}`: Output format (default: summary)
- `--output-file <path>`: Save to specific file path (overrides auto-naming from --re)

### Configuration
- `--library <path>`: Master library root (default: /Volumes/MUSIC/MASTER_LIBRARY)
- `--db <path>`: Path to tagslut database

---

## Notes for Implementation

1. **Backfill is non-destructive:** No downloads happen unless `--force-download`
2. **Metadata harvest can be disabled:** `--no-enrich` flag for speed
3. **DJ pipeline is orthogonal:** Works with any input type
4. **Output formats are composable:** Can export JSON + M3U in same run
5. **Verbose flag is always on:** Only `--quiet` disables console output
