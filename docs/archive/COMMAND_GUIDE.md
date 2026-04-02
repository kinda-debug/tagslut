# Command Guide

## Daily workflow commands

```bash
ts-get <url>              # download: tidal→tiddl, qobuz→streamrip, beatport→beatportdl
ts-get <url> --dj         # download + append to dj_pool.m3u
ts-enrich                 # metadata hoarding: beatport → tidal → qobuz
ts-auth                   # refresh all provider tokens
```

## Token management

```bash
ts-auth tidal             # refresh TIDAL via tiddl
ts-auth beatport          # sync from beatportdl credentials
ts-auth qobuz             # refresh Qobuz app credentials

# When Qobuz user session expires (no auto-refresh):
cd ~/Projects/tagslut && poetry run python -m tagslut auth login qobuz --email EMAIL --force
```

## DJ pool

- `--dj` flag writes two M3U files: one per-batch in the album folder, one at `MP3_LIBRARY/dj_pool.m3u` (accumulates over time)
- Import `dj_pool.m3u` into Rekordbox. Build crates there.
- No `DJ_LIBRARY` folder. No XML emit. No backfill.

## DB query

```bash
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*), SUM(CASE WHEN canonical_genre IS NOT NULL THEN 1 ELSE 0 END) FROM track_identity;"
```

## Legacy reference (RETIRED — 4-stage DJ pipeline)

These commands still work but the workflow is no longer the primary model.
Kept for reference only.

```bash
source START_HERE.sh

# Download a release/track
tools/get <provider-url>

# Lighter run (skip heavier phases intentionally)
tools/get <provider-url> --no-hoard

# Stage 1: Intake masters (creates/refreshes canonical identity state)
poetry run tagslut intake <provider-url>

# Stage 2: Build DJ MP3s from canonical masters (creates MP3s)
poetry run tagslut mp3 build --db "$TAGSLUT_DB" --dj-root "$DJ_LIBRARY" --execute

# Stage 2 alternative: Register existing MP3 root (no re-transcode)
poetry run tagslut mp3 reconcile --db "$TAGSLUT_DB" --mp3-root "$DJ_LIBRARY" --execute

# Stage 3: Admit into curated DJ library
poetry run tagslut dj backfill --db "$TAGSLUT_DB"

# Stage 3 gate: Validate DJ library state
poetry run tagslut dj validate --db "$TAGSLUT_DB"

# Stage 4: Emit Rekordbox XML
poetry run tagslut dj xml emit --db "$TAGSLUT_DB" --out /Volumes/MUSIC/rekordbox_new.xml
```
