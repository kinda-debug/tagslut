# DJ Review App

Local web app to classify Artist / Album / Track as **OK** vs **Not OK**, with web review links and DB-backed decisions.

## Run

```bash
export TAGSLUT_DB="/Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db"
python /Users/georgeskhawam/Projects/tagslut/tools/dj_review_app.py
```

Open: `http://127.0.0.1:5055`

CLI wrapper:

```bash
tagslut dj review-app --db "/Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db"
```

Optional filters:

```bash
export DJ_REVIEW_LIBRARY_PREFIX="/Volumes/MUSIC/LIBRARY"
export DJ_REVIEW_PORT=5055
```

Safe artist defaults (used to pre-fill **OK** buckets when no manual decisions exist):

- `artifacts/dj_safe_artists_overrides.txt`
- `artifacts/dj_safe_artists_from_safe_copy.txt`

Override with:

```bash
export DJ_REVIEW_SAFE_ARTISTS="/path/one.txt,/path/two.txt"
```

## What It Does

- Three tabs: **Artist**, **Album**, **Track**
- Two tall buckets per tab: **OK** and **Not OK**
- Select items and move with arrow buttons
- Evidence panel shows metadata and web review links

## Database Writes

The app creates/updates a table:

```
dj_review_decisions(level TEXT, key TEXT, status TEXT, notes TEXT, updated_at TEXT, source TEXT)
```

Levels:
- `artist`: key is normalized artist name
- `album`: key is `artist|album`
- `track`: key is full file path

## Export OK Tracks

Generate an M3U of all tracks whose **track/album/artist** decision is OK:

```bash
curl -s -X POST http://127.0.0.1:5055/api/export \
  -H 'Content-Type: application/json' \
  -d '{"output": "artifacts/dj_review_ok.m3u8"}'
```

## Build USB From Review

Use the **Export OK → USB** button inside the UI.

Or run manually:

```bash
python /Users/georgeskhawam/Projects/tagslut/tools/dj_usb_sync.py \
  --source /Users/georgeskhawam/Projects/tagslut/artifacts/dj_review_ok.m3u8 \
  --usb /Volumes/MUSIC/DJ \
  --policy /Users/georgeskhawam/Projects/tagslut/config/dj/dj_curation_usb_v8.yaml
```

Pioneer finalize runs by default in `dj_usb_sync.py` (ID3v2.3, artwork cap, Rekordbox XML).

## Web Reviews

The evidence panel provides search links for:
- Beatport
- Resident Advisor
- RateYourMusic
- Discogs
- Bandcamp
- YouTube
- Spotify
- Apple Music

Open the links to evaluate context before moving items.
