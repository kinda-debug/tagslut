# Postman API Optimization — tagslut Beatport Collection

<!-- Status: Active. Update as tasks complete. -->
<!-- Last updated: 2026-03-21 -->
<!-- Commit: 37619ae — 4 files changed, 290 insertions, 0 deletions -->

Collection: `postman/collections/tagslut - Beatport API/`
Environment: `postman/environments/tagslut.environment.yaml`
Globals: `postman/globals/workspace.globals.yaml`
OpenAPI spec: `openapi.json` (Beatport v4)

---

## Completed

- [x] Deleted stale browser-dump collections (`My Collection`, `Beatport`, `BP`)
- [x] Added `base_url = https://api.beatport.com` to environment
- [x] Added `beatport_token_expires_at` to environment
- [x] Token fetch writes expiry timestamp; beforeRequest warns if within 60s
- [x] ISRC Store Lookup: confirmed Basic auth, response shape detection, field logging
- [x] Tracks by ISRC noted as preferred for pipeline ISRC cross-verification
- [x] Track by ID: validates 9 canonical fields, logs 5 bonus fields
- [x] Track by ID: sets `beatport_last_track_id` + `beatport_last_isrc` in env
- [x] Identity Verification folder: `5a` Beatport ISRC lookup + `5b` TIDAL cross-check
- [x] `5b` logs `CORROBORATED` or `CONFLICT: beatport_isrc=X tidal_isrc=Y`
- [x] `5c` Spotify ISRC cross-check — logs `SPOTIFY CORROBORATED`, `CONFLICT`, or `NOT FOUND`
- [x] `spotify_access_token` + `spotify_verified_id` added to environment
- [x] Validation Run folder: `6a` TIDAL album → ISRC seed, `6b` Beatport Track by ID
      with pre-chain ISRC pre-check, `6c` run notes with pass criteria + failure table

---

## Pending operator steps (before Validation Run can execute)

These require manual environment setup — not delegatable to an agent:

1. Add four variables to the `tagslut` environment in Postman desktop
   (patch note at `postman/environments/tagslut.environment.yaml.patch.md`):
   - `spotify_access_token` — obtain via Spotify Client Credentials flow
   - `tidal_seed_track_id`, `tidal_seed_isrc`, `spotify_verified_id` — set at runtime

2. Find the Beatport track ID for the TIDAL seed track:
   - Run `6a` to get the ISRC from the TIDAL album
   - Run `Catalog / Tracks by ISRC` with that ISRC to get `beatport_test_track_id`
   - Set `beatport_test_track_id` in the environment

3. Run the Validation Run folder in Collection Runner in order:
   `6a → 6b → 5a → 5b → 5c`
   Pass criteria: no WARNING on canonical fields, both `5b` and `5c` log `CORROBORATED`

---

## Remaining task

### Task 8 — Collection-level token expiry guard

Add a Collection-level pre-request script that warns if the Beatport token
is within 60 seconds of expiry, so every Bearer-authenticated request
self-checks without requiring per-request scripts.

Script logic:
  const expiresAt = pm.environment.get('beatport_token_expires_at');
  if (expiresAt && Date.now() > (parseInt(expiresAt) - 60000)) {
      console.warn('Beatport token expired or expiring. Re-run Get Token.');
  }

Note: full auto-refresh is not possible at collection level — Postman
pre-request scripts cannot make synchronous fetch calls. The warning
is the correct approach. Document this limitation in the collection
root description.

Commit: `chore(postman): add collection-level token expiry guard`

---

## Commit convention

Each task gets its own commit: `chore(postman): <description>`
