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

Optional filters / defaults:

```bash
export DJ_REVIEW_LIBRARY_PREFIX="/Volumes/MUSIC/LIBRARY"
export DJ_REVIEW_PORT=5055
export DJ_REVIEW_POLICY="config/dj/dj_curation_usb_v8.yaml"
export DJ_REVIEW_USB_PATH="/Volumes/MUSIC/DJ"
export DJ_REVIEW_JOBS=4
export DJ_REVIEW_ARTWORK_MAX_KB=500
export DJ_REVIEW_REKORDBOX_XML="rekordbox.xml"
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
- Track tab includes **auto verdict + reasons** (policy-driven) and quick filters

Note: The UI buckets are still OK / Not OK, but the **auto verdict** can be `review`. Use the Track filters to focus on auto‑review items.

## Auto Verdict (Track Tab)

The app computes an **Auto Verdict** for tracks using `config/dj/dj_curation_usb_v8.yaml`:

- Hard filters: artist blocklist, duration bounds, genre filters
- Scoring: BPM, duration, remix trust, DJ/anti‑DJ genres
- Soft demote to **Review** when metadata is mixed or missing

The evidence panel shows:
- Auto verdict (OK / Review / Not OK)
- Score (if applicable)
- Reasons list

### Track Filters

Filters only apply to the **Track** tab:
- Auto verdict
- Genre contains
- Download source
- BPM min/max
- Duration min/max
- Mismatch only (manual vs auto)

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
