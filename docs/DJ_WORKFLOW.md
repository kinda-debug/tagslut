# DJ Workflow

## Quick Export (Safe Mode)

Once tracks have been classified, just run:

```bash
tagslut dj export --safe --output-root /Volumes/DJUSB
```

Nothing else needed. No prompts.

To export a specific crate:

```bash
tagslut dj export --safe --crate peak-time --output-root /Volumes/DJUSB
```

## Commands

### tagslut dj curate

Preview which tracks pass DJ curation filters (dry run).

Example:

```bash
poetry run tagslut dj curate --input-xlsx /Users/georgeskhawam/Desktop/DJ_YES.xlsx \
  --policy config/dj/dj_curation.yaml \
  --output-root /Volumes/MUSIC/DJ_YES
```

### tagslut dj export

Curate and transcode DJ library to USB output root.

Example:

```bash
poetry run tagslut dj export --input-xlsx /Users/georgeskhawam/Desktop/DJ_YES.xlsx \
  --policy config/dj/dj_curation.yaml \
  --output-root /Volumes/MUSIC/DJ_YES \
  --jobs 4 --detect-keys
```

## DJ Curation Policy Schema

File: `config/dj/dj_curation.yaml`

```yaml
name: dj_curation
version: 2026-02-22.dj_curation.v1
description: DJ curation rules for USB export (duration, blocklists, genre filters).
lane: dj
rules:
  duration_min: 180
  duration_max: 720
  artist_blocklist_path: config/blocklists/non_dj_artists.txt
  artist_reviewlist_path: config/blocklists/borderline_artists.txt
  genre_filters: []
```

## Blocklist Files

- `config/blocklists/non_dj_artists.txt` (hard reject)
- `config/blocklists/borderline_artists.txt` (manual review)

Format: one artist per line, `#` for comments.

## KeyFinder Integration

- Uses `keyfinder-cli` if available on PATH.
- If not installed, key detection is skipped gracefully.
- Enables `--detect-keys` flag for `tagslut dj export`.

## Future

Playlist import as classification source:

`tagslut dj import --source spotify --playlist "DJ Set 2024-08"`

`tagslut dj import --source roon --playlist "Friday Night"`

Every track → verdict=safe, crate=<playlist name>

Requires: Spotify/Tidal API auth, Roon local API
