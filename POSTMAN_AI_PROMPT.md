# Postman AI Agent Task: Rebuild Metadata Collection

## Goal
Rebuild the tagslut API collection to properly validate TIDAL v2 and Beatport as metadata sources for DJ track enrichment.

## Context
Both TIDAL and Beatport expose DJ metadata (bpm, key, genre, label). TIDAL v2 uses JSON:API format. Beatport uses REST. The collection needs credential management, token refresh, and complete metadata field coverage.

## Reference Files in Repo
- `postman/collections/tagslut - API/insomnia-export.1774520966035/TIDAL-API-1.4.8-wrk_957e55c6bbc54239bfc63a150db0d98b.yaml` - Full TIDAL v2 OpenAPI spec (reference)
- Existing requests: `5b - TIDAL ISRC Cross-Check`, `6a - Resolve TIDAL Album to ISRC`

## Metadata Fields to Validate

**TIDAL v2 (openapi.tidal.com/v2):**
- `attributes.bpm`, `attributes.key`, `attributes.keyScale`
- `attributes.toneTags`, `attributes.popularity`, `attributes.explicit`
- `attributes.mediaTags` (audio quality)
- Relationship: `?include=genres` for genre data

**Beatport:**
- `bpm`, `key`, `genre`, `label`, `mix_name`
- `release.label`, `catalog_number`

## Tasks

1. **Update existing TIDAL requests to v2:**
   - `5b - TIDAL ISRC Cross-Check`: Use `openapi.tidal.com/v2/tracks?filter[isrc]={{beatport_verified_isrc}}`
   - `6a - Resolve TIDAL Album to ISRC`: Use `openapi.tidal.com/v2/albums/507881809?include=items`
   - Parse `data[].attributes` not `json.items`

2. **Add credential management:**
   - Beatport: OAuth2 client credentials flow (client_id, client_secret → access_token)
   - TIDAL: Bearer token auth (use existing `tidal_access_token` variable)
   - Auto-refresh tokens when expired

3. **Add validation scripts:**
   - Check all metadata fields present in response
   - Log CORROBORATED (both agree on ISRC) vs CONFLICT
   - Write validated values to environment variables

4. **Environment variables needed:**
   - `beatport_client_id`, `beatport_client_secret` (operator fills in)
   - `beatport_access_token` (auto-populated by auth request)
   - `tidal_access_token` (already exists)

## Expected Outcome
Working Postman collection that validates both TIDAL v2 and Beatport metadata endpoints, handles auth, and confirms which DJ metadata fields each provider returns.
