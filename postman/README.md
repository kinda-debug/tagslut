# Postman exports

This folder stores **sanitized** Postman exports (Collection + Environment) for this repo.

## What lives here

- `postman/collection.json` — exported Postman Collection
- `postman/environment.json` — exported Postman Environment (**no secrets**)
- Optional local-only files (do **not** commit):
  - `postman/environment.secrets.json`
  - `postman/*.local.json`

> Keep secrets out of Git. Postman exports can include tokens and credentials.

---

## Keeping Postman Cloud in sync with this repo

This folder is the Git-tracked “source of truth” for the latest **sanitized** exports:

- `postman/collection.json` ← export of the [tagslut-api](collection/53520441-d3f8de55-e4a7-4728-b3ca-5ee725b60aef) collection
- `postman/environment.json` ← export of the [Metadata Validation Operator (TIDAL v2 + Beatport)](environment/53520441-47ecd53d-7f46-4803-823a-b0b71b513bd8) environment (**no secrets**)

When you change requests / scripts / variables in Postman Cloud, **re-export** into these files so the repo stays in sync.

---

## Export from Postman UI → write to `postman/*.json`

### Export the collection (`postman/collection.json`)

1. In Postman, locate the **tagslut-api** collection.
2. Click **…** (More actions) → **Export**.
3. Choose **Collection v2.1** format.
4. Save/overwrite:
   - `postman/collection.json`

### Export the environment (`postman/environment.json`)

1. In Postman, open **Environments**.
2. Find **Metadata Validation Operator (TIDAL v2 + Beatport)**.
3. Click **Export**.
4. Save/overwrite:
   - `postman/environment.json`

---

## Secrets: don’t commit them

Postman environment exports can include tokens, API keys, refresh tokens, client secrets, etc. Do **not** commit real secret values.

- Use `postman/environment.secrets.example.json` as the template for which secret keys are expected.
- Store real secrets in **Postman Vault** (preferred) or in a local-only file/flow (for example via `postman/env_exports.sh`).

Before committing, open `postman/environment.json` and ensure secret values are placeholders/empty.

---

## Import from `postman/*.json` → Postman UI

### Import the collection

1. In Postman, click **Import**.
2. Select `postman/collection.json`.
3. If prompted, choose the target workspace and complete the import.

### Import the environment

1. In Postman, click **Import**.
2. Select `postman/environment.json`.
3. Set it as the active environment.

---

## Linking Postman runs to tagslut provenance (who/what tagged it)

tagslut v3 writes an audit trail into the `provenance_event` table and stores
identity ingestion attribution on `track_identity.ingestion_*`.

### Field contract + provider authority

- `postman/collection.json` is treated as the **field contract** (the tags you expect to exist on fully-tagged FLACs).
- In code, **Beatport is authoritative for DJ tags** (BPM/key/genre/label) when available. This is the intended validation alignment with the Postman collection.

To attribute Postman/Newman runs to an operator and a run, set these env vars in
the same shell session you use to run Newman and ingest the report:

- `TAGSLUT_OPERATOR` (fallback: `$LOGNAME`/`$USER`)
- `TAGSLUT_RUN_ID` (string; operator-chosen)
- `TAGSLUT_TOOL=postman` (recommended)
- `TAGSLUT_CORRELATION_ID` (optional; stable correlation id for a run)

For CLI intake runs (for example `tools/get --mp3 ...` / `tools/get --dj ...`), set:

- `TAGSLUT_TOOL=cli` (recommended)

### Newman → ingest into v3 DB

1. Run Newman with a JSON report (example):

```bash
export TAGSLUT_OPERATOR="georges"
export TAGSLUT_RUN_ID="postman_$(date +%Y%m%d_%H%M%S)"
export TAGSLUT_TOOL="postman"

newman run postman/collection.json -e postman/environment.json \
  --reporters json --reporter-json-export artifacts/postman/newman_report.json
```

2. Ingest into `provenance_event`:

```bash
poetry run python -m tagslut postman ingest \
  --db "$TAGSLUT_DB" \
  --newman-report artifacts/postman/newman_report.json
```

3. Query attribution:

```bash
poetry run python -m tagslut v3 provenance show --db "$TAGSLUT_DB" --isrc USABC1234567
```


## Update workflow (keeping exports current)

When requests / scripts / variables change:

1. Make and verify your changes in Postman.
2. Re-export:
   - the collection to `postman/collection.json`
   - the environment to `postman/environment.json`
3. **Sanitize before committing** (see below).
4. Commit the updated JSON exports.

---

## Secrets warning (access tokens, API keys)

### What not to commit

Do **not** commit real values for items like:

- `tidal_access_token`
- `beatport_access_token`
- API keys, refresh tokens, client secrets, or passwords

These often appear in exported environment JSON.

### Recommended approach

- Keep `postman/environment.json` committed with **placeholder values** (or empty strings) for secret variables.
- Keep your real secrets in a **local-only** file such as:
  - `postman/environment.secrets.json` (ignored by git)
- Use `postman/environment.secrets.example.json` as the template of which secrets are expected:
  - `tidal_access_token`
  - `beatport_access_token`
  - `spotify_access_token`

If you need to share how to set secrets:

1. Document the variable names (only) in `postman/environment.json`.
2. Provide setup instructions in this README.
3. Each developer fills in secret values locally in Postman (or via a local-only environment export).

> Tip: In Postman, consider keeping secret values in the "Current value" field (local to your account/workspace) and leaving "Initial value" blank/placeholder. Exports can still include values depending on how you export—always review before committing.

---
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
