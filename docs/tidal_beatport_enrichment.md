# TIDAL to Beatport Enrichment

This flow is vendor-only and deterministic:

- TIDAL is intake only.
- Beatport is enrichment only.
- ISRC is the primary join key.
- Title/artist fallback is only used when Beatport ISRC lookup returns no match.
- Unmatched TIDAL rows are preserved in the final CSV with empty Beatport fields.

## Auth

The commands use the repo's existing provider auth surface via `TokenManager` and `~/.config/tagslut/tokens.json`.

Required setup:

```bash
python -m tagslut auth login tidal
python -m tagslut auth login beatport
python -m tagslut auth status
```

Notes:

- TIDAL uses the existing repo OAuth/device-auth flow and refresh-token storage.
- Beatport uses the existing repo token flow; the legacy harvest shell scripts are reference material only and are not called by these commands.

## Commands

Export one stable TIDAL seed CSV from a playlist URL:

```bash
python -m tagslut tidal-seed \
  --playlist-url "https://tidal.com/browse/playlist/..." \
  --out tidal_seed.csv
```

Enrich that seed CSV from Beatport:

```bash
python -m tagslut beatport-enrich \
  --in tidal_seed.csv \
  --out tidal_beatport_enriched.csv
```

If `--out` is omitted for the second command, the default is `tidal_beatport_enriched.csv`.

## Output Columns

The final CSV contains exactly these columns:

- `tidal_playlist_id`
- `tidal_track_id`
- `tidal_url`
- `title`
- `artist`
- `isrc`
- `beatport_track_id`
- `beatport_release_id`
- `beatport_url`
- `beatport_bpm`
- `beatport_key`
- `beatport_genre`
- `beatport_subgenre`
- `beatport_label`
- `beatport_catalog_number`
- `beatport_upc`
- `beatport_release_date`
- `match_method`
- `match_confidence`
- `last_synced_at`

## Match Precedence

1. Beatport `search_by_isrc(isrc)`
2. Beatport `search_by_artist_and_title(artist, title)` only if step 1 yields no match

Match metadata:

- `match_method=isrc`, `match_confidence=1.0`
- `match_method=title_artist_fallback`, `match_confidence=0.6`
- `match_method=no_match`, `match_confidence=0.0`

## Known Failure Modes

- Missing or expired TIDAL auth: seed export returns no rows or fails to fetch playlist items.
- Missing or expired Beatport auth: ISRC lookup may return no results; fallback can still use the provider's existing non-auth search path if available.
- Playlist item shape drift: the parser only extracts the required seed fields and skips unusable rows with debug logging instead of fabricating values.
- Missing ISRC on TIDAL rows: those rows are still exported and can still match through title/artist fallback.
