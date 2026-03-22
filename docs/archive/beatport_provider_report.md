# Beatport Provider Implementation Report

## Files Changed

- `tagslut/metadata/providers/beatport.py`
- `tests/metadata/test_beatport_provider_api.py`
- `tests/fixtures/beatport/catalog_track_list.fixture`
- `tests/fixtures/beatport/catalog_track_detail.fixture`
- `tests/fixtures/beatport/catalog_release_detail.fixture`
- `tests/fixtures/beatport/search_tracks_single.fixture`
- `tests/fixtures/beatport/search_tracks_ambiguous.fixture`

## Endpoint Choices

- Exact-match lookup uses `beatport-v3.json` catalog routes:
  - `GET /v4/catalog/tracks/` with `isrc`
  - `GET /v4/catalog/tracks/{id}/`
  - `GET /v4/catalog/releases/{id}/`
- Fuzzy discovery uses `beatport-search.json` search routes:
  - `GET /search/v1/tracks`
- Optional taxonomy helpers use catalog list routes:
  - `GET /v4/catalog/genres/`
  - `GET /v4/catalog/sub-genres/`
  - `GET /v4/catalog/labels/`

Search is used for candidate generation and ranking. Catalog is used for exact ISRC lookups and detail hydration. Hydrated provider payloads keep `_search`, `_catalog`, and `_release` blocks so provenance stays intact.
Compatibility fallbacks remain on the legacy provider surface:

- `fetch_by_id()` still tries the unauthenticated Next.js track endpoint first
- text search falls back to Beatport web search when official search auth is unavailable or the official search path returns no usable candidates

## Field Mapping Summary

Mapped into `ProviderTrack`:

- `service_track_id` from Beatport track id
- `isrc`
- `title`
- `mix_name`
- `artist` from structured artists arrays
- `album` from release title
- `album_id` from release id
- `catalog_number`
- `track_number` from search `track_number` or catalog `number`
- `bpm`
- `key`
- `genre`
- `sub_genre`
- `label`
- `release_date`
- `duration_ms`
- `preview_url`
- `match_confidence` on ranked text-search results

Preserved in raw provider provenance:

- full search result payload
- full catalog track payload
- full catalog release payload
- availability / streaming flags
- UPC
- additional nested artist / label / genre structures

## Runtime/Auth Notes

- Search service requires bearer auth:
  - `BEATPORT_ACCESS_TOKEN`, or a Beatport token resolved via `TokenManager`
- Catalog service requires either:
  - `BEATPORT_BASIC_AUTH_USERNAME` + `BEATPORT_BASIC_AUTH_PASSWORD`
  - or `BEATPORT_CLIENT_ID` + `BEATPORT_CLIENT_SECRET`
  - or `BEATPORT_SESSIONID`

## Unresolved Gaps

- The checked-in `TokenManager` still documents older Beatport auth assumptions and does not expose first-class helpers for catalog basic auth or session cookies.
- Catalog release hydration assumes release ids can be extracted from either the catalog track payload or the search result payload.
- The provider stays read-only. Library, playlist, and mutation endpoints are intentionally out of scope.
- Search/candidate ranking is deterministic but intentionally minimal: exact title, exact artist, exact mix, provider score, stable track-id tie-break.
- Fallback web-search payloads preserve prior provider behavior but do not carry the enriched `_search` / `_catalog` / `_release` provenance blocks used by the official path.

## Follow-Up Phase Recommendations

- Promote catalog auth configuration into `TokenManager` if Beatport official access becomes a standard runtime dependency.
- Add pagination support for taxonomy helpers if full catalog taxonomies exceed one page.
- Add optional release-by-id helpers if downstream code starts needing release-first workflows.
