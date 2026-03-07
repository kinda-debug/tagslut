# DJ Workflow

DJ pool contract: see `docs/DJ_POOL.md` for the downstream-only boundary and defaults.

## DJ Library Root

Set your DJ library root once and re-use it across workflows:

```bash
set -a
source .env
set +a

export MASTER_LIBRARY="${MASTER_LIBRARY:-${LIBRARY_ROOT:-$VOLUME_LIBRARY}}"
export DJ_LIBRARY="${DJ_LIBRARY:-${DJ_MP3_ROOT:?set DJ_LIBRARY in .env}}"
```

`MASTER_LIBRARY` is the FLAC source of truth. `DJ_LIBRARY` is the derived DJ library. Legacy scripts can still read `LIBRARY_ROOT`, `DJ_MP3_ROOT`, or `DJ_LIBRARY_ROOT` via aliases from `.env`.

## Pipeline Choice

Preferred v3 pipeline (identity-based, deterministic):
- Follow `docs/OPERATIONS.md` for `dj-candidates` → `dj-profile` → `dj-ready` → `dj-pool-plan/run`.
- Use `scripts/dj/build_pool_v3.py` or the `make dj-pool-*` targets for plan/execute.

Legacy v2 pipeline (XLSX/overrides-based):
- Uses `tagslut dj curate/export` with `config/dj/track_overrides.csv`.
- Keep this path only if you are explicitly operating from XLSX inputs.

## Legacy v2 Quick Export (Safe Mode)

Once tracks have been classified, just run:

```bash
tagslut dj export --safe --output-root $DJ_USB_ROOT
```

Nothing else needed. No prompts.

To export a specific crate:

```bash
tagslut dj export --safe --crate peak-time --output-root $DJ_USB_ROOT
```

## Legacy v2 Commands

### tagslut dj curate

Preview which tracks pass DJ curation filters (dry run).

Example:

```bash
poetry run tagslut dj curate --input-xlsx $DJ_XLSX \
  --policy config/dj/dj_curation_usb_v8.yaml \
  --output-root $DJ_USB_ROOT_YES
```

### tagslut dj export

Curate and transcode DJ library to USB output root.

Example:

```bash
poetry run tagslut dj export --input-xlsx $DJ_XLSX \
  --policy config/dj/dj_curation_usb_v8.yaml \
  --output-root $DJ_USB_ROOT_YES \
  --jobs 4 --detect-keys
```

## DJ Curation Policy Schema

Recommended: `config/dj/dj_curation_usb_v8.yaml`

Other policies live in `config/dj/` (v6/v7/relaxed), but v8 is the current tuned default.

```yaml
name: dj_curation_usb_v8
version: 2026-02-25.dj_curation_usb_v8
description: Techno boost + rock nuke (per-genre boost/demote).
lane: dj
rules:
  duration_min: 180
  duration_max: 720
  bpm_min: 110
  bpm_max: 150
  bpm_optimal_min: 118
  bpm_optimal_max: 135
  score_safe_min: 4
  score_block_max: -2
  artist_blocklist_path: config/blocklists/non_dj_artists.txt
  artist_reviewlist_path: config/blocklists/borderline_artists.txt
  genre_filters:
    - experimental
    - jazz
    - blues
    - acoustic
    - folk
  dj_genres:
    - techno
    - tech house
    - melodic house & techno
    - deep tech
    - electronic
    - electronica
    - minimal
    - house
    - deep house
  anti_dj_genres:
    - rock
    - world
    - nu disco / disco
    - dance / pop
    - indie
    - alternative
  genre_boost_mult:
    techno: 2
  genre_demote_mult:
    rock: -20
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

## Review App (Manual Control)

If you want a UI for artist/album/track decisions (OK / Not OK), use the review app:

```bash
tagslut dj review-app --db "$TAGSLUT_DB"
```

See `docs/DJ_REVIEW_APP.md` for auto‑verdict, filters, and USB export.
