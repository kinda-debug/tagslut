# Postman API Optimization — tagslut Beatport Collection

<!-- Status: COMPLETE — all agent tasks done. -->
<!-- Last updated: 2026-03-21 -->
<!-- Final commit: 14c9e29 — 1 file, 42 insertions -->

Collection: `postman/collections/tagslut - Beatport API/`
Environment: `postman/environments/tagslut.environment.yaml`
Globals: `postman/globals/workspace.globals.yaml`
OpenAPI spec: `openapi.json` (Beatport v4)

---

## Completed

- [x] Deleted stale browser-dump collections (`My Collection`, `Beatport`, `BP`)
- [x] Added `base_url = https://api.beatport.com` to environment
- [x] Added `beatport_token_expires_at` + expiry tracking on token fetch
- [x] ISRC Store Lookup: confirmed Basic auth, response shape detection, field logging
- [x] Tracks by ISRC noted as preferred for pipeline ISRC cross-verification
- [x] Track by ID: validates 9 canonical fields, logs 5 bonus fields
- [x] Track by ID: sets `beatport_last_track_id` + `beatport_last_isrc` in env
- [x] Identity Verification: `5a` Beatport ISRC lookup + `5b` TIDAL cross-check
- [x] `5c` Spotify ISRC cross-check — three-way corroboration
- [x] Validation Run folder: `6a` TIDAL seed → `6b` Beatport pre-check → `6c` run notes
- [x] Collection-level token guard (`definition.yaml`) — silent on healthy token,
      warns on expired/expiring, skips auth endpoints to prevent loops

---

## Token guard behaviour (Task 8)

Lives at: `postman/collections/tagslut - Beatport API/.resources/definition.yaml`
Runs before every request in the collection.

| Condition | Output |
|---|---|
| URL is `/v4/auth/o/token/` or `/introspect/` | Silent skip |
| `beatport_access_token` not set | Warns: run Auth / Get Token first |
| Token expired | Logs exact seconds since expiry |
| Token < 60s from expiry | Warns: consider refreshing |
| Token healthy | Silent |

---

## Remaining operator task

Run the Validation Run folder in Collection Runner: `6a → 6b → 5a → 5b → 5c`

Prerequisites:
- Add 4 env variables (see `environments/tagslut.environment.yaml.patch.md`)
- Resolve `beatport_test_track_id` via `Catalog / Tracks by ISRC` using ISRC from `6a`
- Confirm live TIDAL token in environment

Pass criteria: no field WARNINGs, `5b` + `5c` both log `CORROBORATED`
When passed: open PR `dev → main`
