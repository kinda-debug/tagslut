# TIDAL and Beatport Vendor Enrichment
# TIDAL and Beatport Vendor Enrichment

This flow keeps TIDAL and Beatport as peer vendor sources.
This flow keeps TIDAL and Beatport as peer vendor sources.

- Both can be intake sources.
- Both can provide metadata.
- `isrc` is the primary join key.
- Title/artist fallback is only used when ISRC lookup returns no match.
- Raw vendor fields stay in their own source-specific columns.

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
- Beatport seed export uses the authenticated `my/beatport/tracks` library surface.
- Beatport catalog lookup still reuses the current provider logic, including tokenless fallback search where already supported.

## Commands

Export one stable TIDAL playlist seed CSV:
Export one stable TIDAL playlist seed CSV:

```bash
python -m tagslut tidal-seed \
  --playlist-url "https://tidal.com/browse/playlist/..." \
  --out tidal_seed.csv
```

Enrich that TIDAL seed CSV from Beatport:
Enrich that TIDAL seed CSV from Beatport:

```bash
python -m tagslut beatport-enrich \
  --in tidal_seed.csv \
  --out tidal_beatport_enriched.csv
```

Export one stable Beatport library seed CSV:

```bash
python -m tagslut beatport-seed \
  --out beatport_seed.csv
```

Enrich that Beatport seed CSV from TIDAL:

```bash
python -m tagslut tidal-enrich \
  --in beatport_seed.csv \
  --out beatport_tidal_enriched.csv
```

## CSV Shapes

TIDAL seed CSV:

- `tidal_playlist_id`
- `tidal_track_id`
- `tidal_url`
- `title`
- `artist`
- `isrc`

TIDAL -> Beatport merged CSV:

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

Beatport seed CSV:

- `beatport_track_id`
- `beatport_release_id`
- `beatport_url`
- `title`
- `artist`
- `isrc`
- `beatport_bpm`
- `beatport_key`
- `beatport_genre`
- `beatport_subgenre`
- `beatport_label`
- `beatport_catalog_number`
- `beatport_upc`
- `beatport_release_date`

Beatport -> TIDAL merged CSV:

- `beatport_track_id`
- `beatport_release_id`
- `beatport_url`
- `title`
- `artist`
- `isrc`
- `beatport_bpm`
- `beatport_key`
- `beatport_genre`
- `beatport_subgenre`
- `beatport_label`
- `beatport_catalog_number`
- `beatport_upc`
- `beatport_release_date`
- `tidal_track_id`
- `tidal_url`
- `tidal_title`
- `tidal_artist`
- `match_method`
- `match_confidence`
- `last_synced_at`

## Match Order

Both directions follow the same precedence:

1. vendor lookup by `isrc`
2. title/artist fallback only if step 1 yields no match
Beatport seed CSV:

- `beatport_track_id`
- `beatport_release_id`
- `beatport_url`
- `title`
- `artist`
- `isrc`
- `beatport_bpm`
- `beatport_key`
- `beatport_genre`
- `beatport_subgenre`
- `beatport_label`
- `beatport_catalog_number`
- `beatport_upc`
- `beatport_release_date`

Beatport -> TIDAL merged CSV:

- `beatport_track_id`
- `beatport_release_id`
- `beatport_url`
- `title`
- `artist`
- `isrc`
- `beatport_bpm`
- `beatport_key`
- `beatport_genre`
- `beatport_subgenre`
- `beatport_label`
- `beatport_catalog_number`
- `beatport_upc`
- `beatport_release_date`
- `tidal_track_id`
- `tidal_url`
- `tidal_title`
- `tidal_artist`
- `match_method`
- `match_confidence`
- `last_synced_at`

## Match Order

Both directions follow the same precedence:

1. vendor lookup by `isrc`
2. title/artist fallback only if step 1 yields no match

Confidence mapping:
Confidence mapping:

- `match_method=isrc`, `match_confidence=1.0`
- `match_method=title_artist_fallback`, classifier rank mapped to:
- `match_method=title_artist_fallback`, classifier rank mapped to:
  - `exact -> 0.95`
  - `strong -> 0.85`
  - `medium -> 0.70`
  - `weak -> 0.55`
  - `none -> 0.0`
- `match_method=no_match`, `match_confidence=0.0`

## Summary Output

`tidal-seed` prints playlist export counts, malformed/missing/duplicate row counts, page counts, endpoint fallback usage, and pagination stop reasons.

`beatport-enrich` prints input, discarded, written, matched, unmatched, and ambiguity counts.

`beatport-seed` prints exported, missing-ISRC, missing-required, duplicate, page, and pagination-stop counts.

`tidal-enrich` prints input, discarded, written, matched, unmatched, and ambiguity counts.

## Known Limits

- TIDAL playlist export is still playlist-based; it does not enumerate a full TIDAL library.
- Beatport seed export is currently library-based via `my/beatport/tracks`; it does not export arbitrary catalog searches.
- TIDAL reverse lookup prefers exact ISRC when available, then falls back to text search plus client-side scoring.
`tidal-seed` prints playlist export counts, malformed/missing/duplicate row counts, page counts, endpoint fallback usage, and pagination stop reasons.

`beatport-enrich` prints input, discarded, written, matched, unmatched, and ambiguity counts.

`beatport-seed` prints exported, missing-ISRC, missing-required, duplicate, page, and pagination-stop counts.

`tidal-enrich` prints input, discarded, written, matched, unmatched, and ambiguity counts.

## Known Limits

- TIDAL playlist export is still playlist-based; it does not enumerate a full TIDAL library.
- Beatport seed export is currently library-based via `my/beatport/tracks`; it does not export arbitrary catalog searches.
- TIDAL reverse lookup prefers exact ISRC when available, then falls back to text search plus client-side scoring.
- Beatport search remains first-page only for both ISRC and title/artist lookup because it intentionally reuses the current provider methods.
- TIDAL v2 parsing is JSON:API-based; older v1-style payload assumptions such as `tracks.items` and offset pagination are no longer part of the provider contract.
