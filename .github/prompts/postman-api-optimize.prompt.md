You are the Postman AI agent working on the tagslut Beatport + TIDAL API collection.

Goal:
Audit and optimize all API-related requests, scripts, and environment
configuration so the collection reliably supports the tagslut intake
pipeline's provider lookup and identity verification workflows.

Files to read first (all in postman/):
  environments/tagslut.environment.yaml
  globals/workspace.globals.yaml
  collections/tagslut - Beatport API/.resources/definition.yaml
  collections/tagslut - Beatport API/Auth/Get Token (Client Credentials).request.yaml
  collections/tagslut - Beatport API/Auth/Introspect Token.request.yaml
  collections/tagslut - Beatport API/Catalog/Track by ID.request.yaml
  collections/tagslut - Beatport API/Catalog/Tracks by ISRC (query param).request.yaml
  collections/tagslut - Beatport API/Catalog/ISRC Store Lookup (path-based) [Phase 3d].request.yaml
  collections/tagslut - Beatport API/Catalog/Release by ID.request.yaml
  collections/tagslut - Beatport API/Catalog/Release Tracks.request.yaml
  collections/tagslut - Beatport API/My Library/My Beatport Tracks.request.yaml
  collections/tagslut - Beatport API/My Library/My Account.request.yaml
  collections/tagslut - Beatport API/Search/Search Tracks by Text.request.yaml

Also read for pipeline context:
  openapi.json  (Beatport v4 OAS — authoritative spec for all endpoints)


Pipeline context:
  The tagslut intake pipeline uses the Beatport API as a primary identity
  anchor. When `tools/get --enrich <url>` runs:
    1. pre_download_check.py resolves track IDs from the Beatport URL
    2. Each track is looked up by Beatport ID to get ISRC, artist, title,
       BPM, key, genre, label, catalog number
    3. The ISRC is used to cross-verify against TIDAL
    4. When both providers confirm the same ISRC, the identity is written
       with ingestion_method='provider_api', ingestion_confidence='verified'

  The canonical field mapping from Beatport API response to tagslut DB:
    beatport_id       → track.id
    isrc              → track.isrc
    canonical_title   → track.name
    canonical_artist  → track.artists[].name (all names joined)
    canonical_bpm     → track.bpm
    canonical_key     → track.key.name
    canonical_genre   → track.genre.name
    canonical_label   → track.release.label.name
    canonical_mix_name → track.mix_name


Tasks — complete all of these:

1. ENVIRONMENT: Fix missing and stale variables
   Add to tagslut.environment.yaml:
     base_url              https://api.beatport.com
     beatport_token_expires_at  (empty string, for expiry tracking)
   Confirm every request uses {{base_url}} not a hardcoded URL.
   Add STAGING_ROOT deprecation note: VOLUME_STAGING is deprecated,
   use STAGING_ROOT instead (do not change the env file for this —
   just document it in the collection description).

2. AUTH: Token lifecycle management
   In Get Token (Client Credentials).request.yaml:
     - The afterResponse script sets beatport_access_token — confirm it works
     - Add expiry tracking: after setting the token, also set
       beatport_token_expires_at to (Date.now() + json.expires_in * 1000)
     - Add a pre-request script that checks if the token is within 60
       seconds of expiry and re-fetches automatically if so
   In Introspect Token.request.yaml:
     - Confirm the introspect endpoint exists in the OAS spec
     - If it does not exist in the spec, mark the request as DEPRECATED
       in its description

3. ISRC LOOKUP: Resolve the open auth question
   The Phase 3d ISRC Store Lookup has an unresolved question:
   does it require Bearer, cookie, or basic auth?
   - Read the OAS spec (openapi.json) for /v4/catalog/tracks/store/{isrc}/
   - Update the request description with the confirmed auth method
   - Update the afterResponse script to validate the response shape:
     * Is it a direct record (has 'id', 'isrc' at top level)?
     * Or a paginated wrapper (has 'results', 'count')?
   - Compare with Tracks by ISRC (query param) — document which returns
     richer metadata and which should be preferred by the pipeline

4. TRACK BY ID: Validate canonical field coverage
   Add an afterResponse test script that:
     - Checks all nine canonical fields are present in the response
       (id, isrc, name, artists, bpm, key, genre, release.label, mix_name)
     - Logs a WARNING for each field that is null or missing
     - Sets pm.environment.set('beatport_last_track_id', json.id) for
       chaining into release lookups

5. MY BEATPORT TRACKS: Pagination and token scope
   - Add pre-request script: set page=1, page_size=100 as query params
   - Add afterResponse script: log pm.response.json().count (total tracks)
     and whether next/previous pages exist
   - Document in the request description whether this endpoint requires
     a user-scoped token (PKCE flow) vs client credentials
   - If client credentials are insufficient, add a note on how to obtain
     a user token via the TIDAL PKCE flow already configured in .env

6. COLLECTION DOCUMENTATION
   Add a root-level description to the collection covering:
     a. Auth order: run Get Token first, then any Catalog/My Library request
     b. Which endpoints need client credentials vs user token
     c. The canonical field mapping table (from Pipeline context above)
     d. How to test a full identity lookup:
        Get Token → Track by ID (set beatport_test_track_id) →
        ISRC lookup → cross-verify with TIDAL

7. COMMIT
   After all changes:
     git add postman/
     git commit -m "chore(postman): optimize Beatport API collection — auth lifecycle, ISRC resolution, field validation"
     git push
