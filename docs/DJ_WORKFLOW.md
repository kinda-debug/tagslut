<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

# DJ Workflow

DJ pool contract: see `docs/DJ_POOL.md` for the downstream-only boundary and defaults.

## Downloader Shortcut

For new downloads that should flow all the way into the DJ library, start with:

```bash
tools/get <provider-url> --dj
```

That runs precheck, download, tagging/enrichment, promote, merged M3U generation, and DJ MP3 export in one flow.
Use `--verbose` only when you want internal wrapper diagnostics.

## DJ Library Root

Set your DJ library root once and re-use it across workflows:

```bash
set -a
source .env
set +a

export MASTER_LIBRARY="${MASTER_LIBRARY:-${LIBRARY_ROOT:-$VOLUME_LIBRARY}}"
export PLAYLIST_ROOT="${PLAYLIST_ROOT:-$MASTER_LIBRARY/playlists}"
export DJ_LIBRARY="${DJ_LIBRARY:-${DJ_MP3_ROOT:?set DJ_LIBRARY in .env}}"
export DJ_PLAYLIST_ROOT="${DJ_PLAYLIST_ROOT:-$DJ_LIBRARY}"
```

`MASTER_LIBRARY` is the FLAC source of truth. `PLAYLIST_ROOT` holds Roon-readable library playlists. `DJ_LIBRARY` is the derived DJ library, and `DJ_PLAYLIST_ROOT` holds DJ playlists with absolute paths for Rekordbox/Lexicon workflows. Legacy scripts can still read `LIBRARY_ROOT`, `DJ_MP3_ROOT`, or `DJ_LIBRARY_ROOT` via aliases from `.env`.

## Pipeline Choice

Preferred v3 pipeline (identity-based, deterministic):
- Follow `docs/OPERATIONS.md` for `dj-candidates` → `dj-profile` → `dj-ready` → `dj-pool-plan/run`.
- Use `scripts/dj/build_pool_v3.py` or the `make dj-pool-*` targets for plan/execute.

Legacy v2 pipeline (XLSX/overrides-based):
- Uses `tagslut dj curate/export` with `config/dj/track_overrides.csv`.
- Keep this path only if you are explicitly operating from XLSX inputs.

## DJ Pool Wizard

`tagslut dj pool-wizard` is the primary operator workflow for building a final MP3 DJ pool from `MASTER_LIBRARY`.

### Usage

Plan-first, non-interactive:

```bash
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_LIBRARY" \
  --out-root /tmp/dj_pool_runs \
  --non-interactive \
  --profile config/dj/pool_profile.json
```

Interactive TTY wizard:

```bash
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_LIBRARY" \
  --out-root /tmp/dj_pool_runs
```

What it does:

- locks the cohort to flagged tracks under `MASTER_LIBRARY`
- writes cohort health, duplicate analysis, selected rows, plan rows, and manifest artifacts into a timestamped run directory
- uses relinked or cached MP3 sources when available, and only transcodes on execute when no reusable MP3 source exists
- keeps `--plan` mutation-free; file copies and DB writes only happen under `--execute`

Use `scripts/dj/build_pool_v3.py` only as the lower-level script path when you need the script-level builder directly. Operator docs should point to `tagslut dj pool-wizard`.

## Staged-Root DJ Phase

For an already-staged FLAC root, `process-root` now has a DJ phase:

```bash
python -m tagslut intake process-root \
  --db "$V3_DB" \
  --root "$STAGING_ROOT" \
  --phases dj \
  --dry-run
```

What it does:

- looks up the active identity for each staged FLAC
- writes BPM and key from v3 canonical identity data when available
- falls back to Essentia for BPM/key/energy when canonical values are missing
- transcodes staged FLACs to the configured DJ pool when not in dry-run mode

Notes:
- `--dry-run` currently previews the DJ phase only
- if Essentia is not installed, fallback analysis is skipped with a warning
- the deterministic v3 builder path is still the preferred export route for a curated DJ pool

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
