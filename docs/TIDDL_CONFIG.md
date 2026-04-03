# tiddl Configuration — tagslut workspace

<!-- Status: Active. Update when tiddl version or template strategy changes. -->
<!-- Last updated: 2026-03-21 -->
<!-- tiddl version: 3.x (v3.2.2 at time of writing) -->

Config file: `~/.tiddl/config.toml`
Source: `~/Desktop/tiddl_config.toml` (committed reference copy)
tiddl docs: https://github.com/oskvr37/tiddl/blob/main/docs/templating.md

---

## Why this config exists

tiddl ships with a minimal default template (`{album.artist}/{album.title}/{item.title}`)
that produces no identity anchors in filenames. tagslut's intake pipeline needs the ISRC
in every downloaded filename so that each file is self-describing even before the DB scan.

This config also sets `track_quality = "max"` to match the MASTER_LIBRARY 24-bit standard,
and leaves `download_path` and `scan_path` unset so the `tools/tiddl` wrapper can manage
them at runtime via `sync_tiddl_config_paths()`.

---

## Installation

```bash
mkdir -p ~/.tiddl
cp ~/Desktop/tiddl_config.toml ~/.tiddl/config.toml
```

The `tools/tiddl` wrapper will update `download_path` and `scan_path` automatically
on each run based on the resolved `$ROOT_TD` / `$STAGING_ROOT` env values.

---

## Template strategy

Every template includes `{item.isrc}` in the filename. This is the core decision.

**Why ISRC in the filename:**
- tiddl writes `ISRC` to the FLAC tag at download time (sourced from TIDAL API)
- tagslut reads that tag at scan time for cross-provider verification
- Having ISRC in the filename means the file is self-describing outside the DB
- It survives path reorganization, drive moves, and epoch migrations
- Files downloaded via tiddl get `ingestion_method='provider_api'` and
  `ingestion_confidence='high'` — the ISRC in the filename makes that verifiable

**Why `{item.artists}` not `{item.artist}`:**
`format.py` builds `artists` as a sorted comma-joined list of all MAIN artists,
which is exactly what `add_track_metadata()` writes to the ARTIST FLAC tag.
This matches tagslut's `canonical_artist` field. `item.artist` is only the primary
artist from `item.artist.name` — incomplete for multi-artist tracks.


---

## Templates

### `track` — single track download

```
{item.artists} - {item.title} [{item.isrc}]
```

Example: `Ricardo Villalobos - Enfants [DEABC1234567].flac`

Used when: `tiddl download url <track_url>` or `tools/tiddl <track_url>`

### `album` — album download (primary use case)

```
{album.artist}/{album.title}/{item.number:02d}. {item.artists} - {item.title} [{item.isrc}]
```

Example:
```
Plastikman/Sheet One/
  01. Plastikman - Spastik [CADEF9876543].flac
  02. Plastikman - Gak [CADEF9876544].flac
```

Used when: `tools/get --enrich <album_url>` triggers tiddl for TIDAL albums.
`item.number:02d` zero-pads the track number for correct filesystem sort order.

### `playlist` — playlist download

```
{playlist.title}/{playlist.index:04d}. {item.artists} - {item.title} [{item.isrc}]
```

Example:
```
My Favorites/
  0001. Basic Channel - Quadrant Dub [DEAAA1111111].flac
  0002. Drexciya - Aquatacizem [USAAA2222222].flac
```

`playlist.index:04d` zero-pads to 4 digits — supports playlists up to 9999 tracks.

Note from tiddl docs: if the template uses `{album...}` fields in a playlist context,
tiddl makes one additional API request per album to fetch album data. The album data
is cached, so only one request per unique album. See tiddl issue #217.

### `mix` — mix download

```
{item.artists} - {item.title} [{item.isrc}]
```

Same flat format as single tracks. `{mix_id}` is available as an extra variable
but produces unhelpful UUID-style folder names.

### `default` — fallback

```
{album.artist}/{album.title}/{item.artists} - {item.title} [{item.isrc}]
```

No track number prefix — used only when the media type doesn't match a specific
template. Should rarely fire in normal tagslut usage.


---

## Full template variable reference (tiddl v3)

Sourced from `tiddl/core/utils/format.py` and `docs/templating.md`.

### `item` — Track or Video

| Variable | Type | Source in format.py | Notes |
|---|---|---|---|
| `{item.id}` | int | `item.id` | TIDAL track ID — maps to `tidal_id` in `track_identity` |
| `{item.title}` | str | `item.title` | Raw title without version |
| `{item.title_version}` | str | `f"{title} ({version})"` | Title + version if present |
| `{item.number}` | int | `item.trackNumber` | Supports format spec e.g. `:02d` |
| `{item.volume}` | int | `item.volumeNumber` | Disc number |
| `{item.version}` | str | `item.version or ""` | Version string e.g. `Remastered` |
| `{item.copyright}` | str | `item.copyright or ""` | Track only |
| `{item.bpm}` | int | `item.bpm or 0` | Track only, 0 if unavailable |
| `{item.isrc}` | str | `item.isrc or ""` | ISRC code — same value written to FLAC tag |
| `{item.quality}` | str | passed as `quality=` arg | `HIGH` or `MAX` |
| `{item.artist}` | str | `item.artist.name` | Primary artist only |
| `{item.artists}` | str | sorted MAIN artists, joined | Matches ARTIST FLAC tag |
| `{item.features}` | str | sorted FEATURED artists | Featured only |
| `{item.artists_with_features}` | str | MAIN + FEATURED | Full credit string |
| `{item.explicit}` | Explicit | `item.explicit` | Format spec: default=`E`, `:long`=`explicit`, `:full`=`explicit`/`clean` |
| `{item.dolby:TEXT}` | UserFormat | `"DOLBY_ATMOS" in mediaMetadata.tags` | Renders TEXT if Dolby Atmos, empty otherwise |

### `album`

| Variable | Type | Source in format.py | Notes |
|---|---|---|---|
| `{album.id}` | int | `album.id` | TIDAL album ID |
| `{album.title}` | str | `album.title` | |
| `{album.artist}` | str | `album.artist.name` | Primary artist |
| `{album.artists}` | str | MAIN artists joined | |
| `{album.date}` | datetime | `album.releaseDate` | Supports strftime: `{album.date:%Y}` = year only |
| `{album.explicit}` | Explicit | `album.explicit` | Same format spec as item.explicit |
| `{album.master:TEXT}` | UserFormat | `HIRES_LOSSLESS in tags AND quality==MAX` | Renders TEXT only for true hi-res max quality |
| `{album.release}` | str | `album.type` | `ALBUM`, `EP`, or `SINGLE` |

### `playlist`

| Variable | Type | Source in format.py | Notes |
|---|---|---|---|
| `{playlist.uuid}` | str | `playlist.uuid` | Full UUID |
| `{playlist.title}` | str | `playlist.title` | |
| `{playlist.index}` | int | `playlist_index` arg | Position in playlist. Supports `:04d` |
| `{playlist.created}` | datetime | `datetime.fromisoformat(playlist.created)` | Supports strftime |
| `{playlist.updated}` | datetime | `datetime.fromisoformat(playlist.lastUpdated)` | Supports strftime |

### Special

| Variable | Notes |
|---|---|
| `{now}` | Current datetime at download time. Supports strftime: `{now:%Y-%m-%d}` |
| `{mix_id}` | Passed as `**extra` for mix downloads. UUID-style string. |

---

## Download settings

| Setting | Value | Reason |
|---|---|---|
| `track_quality` | `max` | MASTER_LIBRARY standard: 24-bit FLAC up to 192kHz |
| `skip_existing` | `true` | Idempotent downloads — `tools/tiddl` relies on this |
| `threads_count` | `4` | Conservative. Increase if TIDAL rate limits are not an issue |
| `update_mtime` | `true` | Allows detection of files removed from TIDAL collections |
| `rewrite_metadata` | `false` | tagslut owns metadata writeback via `canonical_writeback.py` |
| `metadata.cover` | `true` | Embeds cover art in FLAC at download time |
| `metadata.lyrics` | `false` | Not used in tagslut workflow |
| `download_path` | unset | Managed at runtime by `tools/tiddl` `sync_tiddl_config_paths()` |
| `scan_path` | unset | Same — must not be hardcoded here |

---

## Relationship to tools/tiddl wrapper

The `tools/tiddl` wrapper (`SCRIPT_DIR/tiddl`) manages two concerns this config does not:

1. **Path injection**: `sync_tiddl_config_paths()` writes `download_path` and `scan_path`
   into `~/.tiddl/config.toml` at runtime based on `$ROOT_TD` / `$STAGING_ROOT` env values.
   Do not hardcode these in `config.toml` — they will be overwritten.

2. **Quality override**: The wrapper passes `-q max` by default unless `--track-quality`
   is explicitly provided. This is redundant with `track_quality = "max"` in the config
   but ensures correct behavior even if the config is missing.

---

## FLAC tags written by tiddl at download time

From `tiddl/core/track.py` (`add_track_metadata` → `add_flac_metadata`):

| FLAC tag | Source | tagslut mapping |
|---|---|---|
| `TITLE` | `track.title (+ version if present)` | `canonical_title` |
| `ARTIST` | sorted MAIN artists, comma-joined | `canonical_artist` |
| `ALBUMARTIST` | `album_artist` arg | album-level artist |
| `ALBUM` | `track.album.title` | `canonical_album` |
| `TRACKNUMBER` | `track.trackNumber` | |
| `DISCNUMBER` | `track.volumeNumber` | |
| `DATE` / `YEAR` | `album.releaseDate` | `canonical_year` |
| `ISRC` | `track.isrc` | `ingestion_source` anchor |
| `BPM` | `track.bpm` | `canonical_bpm` |
| `COPYRIGHT` | `track.copyright` | |
| `COMMENT` | `comment` arg | |

These tags are written before tagslut's scan. tagslut reads them at scan time
and uses ISRC as the primary identity anchor for `ingestion_method='provider_api'`.

---

## Cover art configuration (updated 2026-03-21)

### Embedded cover (metadata)
`[metadata] cover = true` — tiddl embeds cover art in every FLAC file. Always on.

### Separate cover file
The correct configuration places the cover file INSIDE the album folder,
not at the staging root level:

```toml
[cover]
save = true
size = 1280
allowed = ["album"]

[cover.templates]
album = "{album.artist}/{album.title}/cover"
```

This produces:
```
Various Artists/20 Years of Lazy Days/
  01. Artist - Title [ISRC].flac
  02. Artist - Title [ISRC].flac
  cover.jpg                          ← inside the folder
```

Without the template, tiddl writes `cover.jpg` to the staging root (outside
the album folder), which breaks album-level organization.

---

## What tiddl does and does not write

### Written by tiddl at download time (from TIDAL API)
TITLE, ARTIST, ALBUMARTIST, ALBUM, TRACKNUMBER, DISCNUMBER, DATE, YEAR,
COPYRIGHT, ISRC, COMMENT, BPM (if non-null in API response), cover art (embedded)

### NOT written by tiddl — requires tagslut enrichment pass
- **Genre** — not in TIDAL v1 API track response
- **Key** — not in TIDAL v1 API track response
- **BPM** — TIDAL returns null for many tracks; Beatport is the reliable source
- **Label** — available via album API but not written to tags by tiddl
- **Catalog number** — same

These fields are populated by tagslut's enrichment pass (primarily via Beatport).
Separately, tagslut also captures TIDAL-native DJ fields (when present in the
TIDAL provider payload) into v3 `track_identity` for auditing/identity use:
`tidal_bpm`, `tidal_key`, `tidal_key_scale`, `tidal_camelot`, `replay_gain_*`,
`tidal_dj_ready`, `tidal_stem_ready`.
