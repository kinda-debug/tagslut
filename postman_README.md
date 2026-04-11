# tagslut Postman — Executable Prompts

**These are the actual workflows. Copy-paste them directly.**

---

## Setup: Validate credentials

```bash
# 1. Check Beatport auth
curl -s https://api.beatport.com/v4/me \
  -H "Authorization: Bearer $BEATPORT_TOKEN" | jq '.name'

# 2. Check Tidal auth
curl -s https://api.tidal.com/v1/sessions \
  -H "X-Tidal-Token: $TIDAL_TOKEN" | jq '.sessionId'

# 3. Check Discogs auth
curl -s https://api.discogs.com/user \
  -H "Authorization: Discogs token=$DISCOGS_TOKEN" | jq '.username'
```

**Expected:** Three usernames or session IDs. If any fail, the token is dead.

---

## Workflow 1: Verify a track across providers

**Input:** One Beatport track ID or URL  
**Output:** ISRC + provider IDs from Beatport, Tidal, Spotify, Discogs

```bash
# Get Beatport metadata
BP_TRACK_ID="12345678"
BP_DATA=$(curl -s "https://api.beatport.com/v4/tracks/$BP_TRACK_ID" \
  -H "Authorization: Bearer $BEATPORT_TOKEN" | jq '.')

BP_ISRC=$(echo "$BP_DATA" | jq -r '.isrc')
BP_TITLE=$(echo "$BP_DATA" | jq -r '.title')
echo "Beatport ISRC: $BP_ISRC | Title: $BP_TITLE"

# Cross-check Tidal
TIDAL_DATA=$(curl -s "https://api.tidal.com/v2/tracks?filter[isrc]=$BP_ISRC&countryCode=US" \
  -H "Authorization: Bearer $TIDAL_TOKEN" | jq '.data[0]')

echo "Tidal match: $(echo "$TIDAL_DATA" | jq -r '.attributes.title // "NO MATCH"')"
echo "Tidal ID: $(echo "$TIDAL_DATA" | jq -r '.id')"

# Cross-check Spotify
SPOTIFY_DATA=$(curl -s "https://api.spotify.com/v1/search?q=isrc:$BP_ISRC&type=track&limit=1" \
  -H "Authorization: Bearer $SPOTIFY_TOKEN" | jq '.tracks.items[0]')

echo "Spotify match: $(echo "$SPOTIFY_DATA" | jq -r '.name // "NO MATCH"')"
echo "Spotify ID: $(echo "$SPOTIFY_DATA" | jq -r '.id')"
```

---

## Workflow 2: Intake a single track to DJ_LIBRARY

**Input:** Beatport or Tidal URL  
**Output:** Full-tag MP3 in `/Volumes/MUSIC/MP3_LIBRARY/` and minimal-tag DJ copy in `/Volumes/MUSIC/DJ_LIBRARY/`

```bash
URL="https://www.beatport.com/track/example/12345678"
tools/get --dj "$URL" --verbose

# Check outputs
ls -lh /Volumes/MUSIC/MP3_LIBRARY/**/*.mp3 2>/dev/null | tail -5
ls -lh /Volumes/MUSIC/DJ_LIBRARY/**/*.mp3 2>/dev/null | tail -5

# 3. Read metadata
mediainfo /Volumes/MUSIC/MP3_LIBRARY/latest_track.mp3 | grep -E "ISRC|Title|Artist"
```

---

## Workflow 3: Build all MP3s from MASTER_LIBRARY

**Input:** FLAC files in `/Volumes/MUSIC/MASTER_LIBRARY`  
**Output:** 320kbps MP3 copies with metadata in `/Volumes/MUSIC/MP3_LIBRARY/`

```bash
# 1. Dry-run to see what will build
tools/mp3 --batch 50 --dry-run

# 2. Actually build them
tools/mp3 --batch 50

# 3. Monitor progress
watch -n 2 'ls -lh /Volumes/MUSIC/MP3_LIBRARY | tail -20'

# 4. Verify metadata on a sample
mediainfo /Volumes/MUSIC/MP3_LIBRARY/Artist/Album/01*.mp3 | grep -A 5 "ISRC"
```

---

## Workflow 4: Find truncated tracks in MASTER_LIBRARY

**Input:** None (scans entire library)  
**Output:** List of files with mismatched duration

```bash
# 1. Compare actual duration vs expected (from metadata sources)
tools/get --verify-integrity --all --report truncated_tracks.csv

# 2. Read the report
cat /Volumes/MUSIC/artifacts/truncated_tracks.csv | head -20

# 3. For each truncated file, get the expected duration from providers
ISRC="USXXXXXXXXXXXXX"
curl -s "https://api.beatport.com/v4/tracks?isrc=$ISRC" \
  -H "Authorization: Bearer $BEATPORT_TOKEN" | jq '.results[0] | {title, duration}'
```

---

## Workflow 5: Sync dedupe database with MASTER_LIBRARY

**Input:** MASTER_LIBRARY on disk  
**Output:** Updated dedupe index in `$TAGSLUT_DB`

```bash
# 1. Scan for new files and fingerprints
poetry run python -m tagslut index scan /Volumes/MUSIC/MASTER_LIBRARY \
  --db /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db \
  --progress --workers 8

# 2. Check what was found
sqlite3 /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db \
  "SELECT COUNT(*) as total, COUNT(DISTINCT isrc) as unique_isrcs FROM track_identity;"

# 3. Find duplicates by fingerprint
sqlite3 /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db \
  "SELECT fpcalc_result, COUNT(*) as count FROM files WHERE fpcalc_result IS NOT NULL \
   GROUP BY fpcalc_result HAVING count > 1 ORDER BY count DESC LIMIT 20;"
```

---

## Workflow 6: Export for Rekordbox (DJ)

**Input:** DJ_LIBRARY  
**Output:** Rekordbox XML

```bash
# 1. Generate XML from DJ collection
tools/dj xml emit /Volumes/MUSIC/DJ_LIBRARY > rekordbox_export.xml

# 2. Verify XML is well-formed
xmllint --noout rekordbox_export.xml && echo "✓ Valid XML"

# 3. Check track count
grep -c "<TRACK" rekordbox_export.xml

# 4. Import into Rekordbox (manual step):
# Rekordbox → File → Import → Select rekordbox_export.xml
```

---

## Debugging: Get actual error logs

**The pretty output is useless. Use these instead:**

```bash
# Raw intake log
tail -100 /Users/georgeskhawam/Projects/tagslut/artifacts/intake/logs/get_intake_*.log

# Why did a track get skipped?
grep -A 2 "InputSkipped" /Users/georgeskhawam/Projects/tagslut/artifacts/intake/logs/*.log

# What was the fingerprint result for a specific file?
sqlite3 /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db \
  "SELECT file_path, fpcalc_result, integrity_status FROM files \
   WHERE file_path LIKE '%artist_name%' LIMIT 5;"

# Check metadata harvest status
sqlite3 /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db \
  "SELECT COUNT(*) as verified, COUNT(*) as high, COUNT(*) as uncertain \
   FROM track_identity WHERE ingestion_confidence IN ('verified', 'high', 'uncertain');"
```

---

## Common issues

| Problem | Command |
|---------|---------|
| Files not moving from staging | `ls /Volumes/MUSIC/staging/tidal \| wc -l` — if > 0, clear it: `rm -rf /Volumes/MUSIC/staging/tidal/*` |
| Token expired | Re-auth: `tiddl auth` then `poetry run python tagslut/exec/refresh_auth.py` |
| Truncated files detected | Run Workflow 4 above to identify them |
| MP3s not getting metadata | Check: `mediainfo /Volumes/MUSIC/MP3_LIBRARY/sample.mp3 \| grep ISRC` |
| Duplicate ISRC in DJ_LIBRARY | `sqlite3 $TAGSLUT_DB "SELECT isrc, COUNT(*) FROM track_identity WHERE zone='DJ' GROUP BY isrc HAVING COUNT(*) > 1;"` |

---

## Environment check

```bash
# Verify all paths exist
for vol in MUSIC SAD; do
  if [ -d "/Volumes/$vol" ]; then
    echo "✓ /Volumes/$vol mounted"
  else
    echo "✗ /Volumes/$vol NOT mounted"
  fi
done

# Verify credentials are set
for var in BEATPORT_TOKEN TIDAL_TOKEN SPOTIFY_TOKEN DISCOGS_TOKEN; do
  if [ -n "${!var}" ]; then
    echo "✓ $var set"
  else
    echo "✗ $var missing"
  fi
done

# Verify DB exists
if [ -f "$TAGSLUT_DB" ]; then
  echo "✓ $TAGSLUT_DB exists ($(sqlite3 $TAGSLUT_DB 'SELECT COUNT(*) FROM sqlite_master;') tables)"
else
  echo "✗ $TAGSLUT_DB missing"
fi
```

---

## Next steps

1. **Run the environment check above.** Fix any ✗ before continuing.
2. **Pick a Beatport track you know is good.** Run Workflow 1 to verify it exists on Tidal/Spotify.
3. **If Workflow 1 succeeds, run Workflow 2.** Intake one track to DJ_LIBRARY.
4. **Check the actual log** (not the pretty box output): `tail -50 /Users/georgeskhawam/Projects/tagslut/artifacts/intake/logs/*.log`
5. **If that works, run `tools/mp3`** to build the full MP3 library.

**No more box-drawing output.** Just actual commands and actual results.
