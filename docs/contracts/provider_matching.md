# Provider Matching Contract

**Status:** Normative  
**Anchored to:** commit `a060a2b` + local repo state 2026-03-19  
**Supersedes:** `Dual-SourceTIDALBeatportMetadataFlow.md`, `docs/beatport_provider_report.md`

---

## Provider Scope

Two providers only: **TIDAL** and **Beatport**. All others are out of scope.

---

## TIDAL Provider (`tagslut/metadata/providers/tidal.py`)

### Transport split

| Method | Transport | ISRC Capable | Notes |
|--------|-----------|--------------|-------|
| `fetch_by_id()` | v2 JSON:API (`openapi.tidal.com/v2`) | N/A (ID lookup) | |
| `search_by_isrc()` | v2 JSON:API | **Yes** — `filter[isrc]` on `GET /tracks` | |
| `search()` | v2 JSON:API | No | Text search via `searchResults` endpoint |
| `_tidal_v1_get()` / playlist export | v1 legacy (`api.tidal.com/v1`) | **No** | Legacy path, no migration without parity validation |

### Auth

- **Flow:** Authorization Code with PKCE
- **Status:** Working. Tokens valid. Callback confirmed.
- **Valid scopes:** `entitlements.read search.read`
- **Invalid legacy scopes:** `r_usr`, `w_usr` — these cause auth failure, do not use
- **Token storage:** `tidal_tokens.json` (local only, gitignored)

### ISRC capability

v2 `search_by_isrc()` uses `filter[isrc]` on `GET /v2/tracks`. This is a server-side filter, not client-side text search. ISRC-capable on the v2 path.

The v1 playlist export path has no ISRC capability. This is a known limitation of the legacy transport, not a platform constraint.

---

## Beatport Provider (`tagslut/metadata/providers/beatport.py`)

### Auth modes

| Auth Kind | Credential | Used For |
|-----------|-----------|---------|
| `catalog` | Session cookie (`sessionid`) or Basic auth (client_id/client_secret) | `/v4/catalog/` endpoints including ISRC search |
| `search` | Bearer token (`BEATPORT_ACCESS_TOKEN`) | `/search/v1/tracks` |
| None | — | Next.js data endpoints, web scraping, Beatsource migrator |

### ISRC capability

| Method | Auth Required | ISRC Capable | Notes |
|--------|--------------|--------------|-------|
| `search_track_by_isrc()` | Yes (catalog) | **Yes** — `GET /v4/catalog/tracks/?isrc=` | Falls back to empty list if auth absent |
| `/v4/catalog/tracks/store/{isrc}/` | Yes (catalog) | **Yes** — path-based lookup | **Discovered in OAS, untested. High priority (O3).** |
| `search_track_by_text()` | Yes (search bearer) | No | Falls back to web scraping if auth absent |
| Web scraping (`_search_web()`) | No | No | Fallback only |
| Beatsource migrator | No | No | ID mapping only |

**Auth-absent degradation:** When catalog auth is missing, `search_track_by_isrc()` returns empty and `search_track_by_text()` falls back to web scraping. Both log a `WARNING` (after Phase 3c fix). ISRC matching is silently disabled without auth.

### `/v4/catalog/tracks/store/{isrc}/` endpoint

Discovered in Beatport v4 OAS. Path-based ISRC lookup, distinct from query-parameter approach. If it returns a direct track record without pagination, prefer it over `?isrc=` query parameter.

**Status:** Untested. Test with a known ISRC before switching. Keep query-parameter as fallback. See Postman request: `Beatport - ISRC Store Lookup`.

---

## Match Precedence

For both providers, resolution order is:

1. **ISRC** — exact match, highest confidence (`EXACT`)
2. **Title/artist fallback** — ranked by `classify_match_confidence()`, confidence varies
3. **No match** — `MatchConfidence.NONE`

### Confidence classification

`classify_match_confidence()` in `base.py` returns a `MatchConfidence` enum. Numeric serialization uses `CONFIDENCE_NUMERIC` from `types.py`. See `metadata_architecture.md` for the mapping table.

---

## Rate Limits

| Provider | `min_delay` | `max_retries` | `base_backoff` |
|----------|------------|---------------|----------------|
| Beatport | 0.5s | 3 | 2.0s |
| TIDAL | 0.4s | 3 | 2.0s |

Beatport returns `Retry-After` header on 429. Both providers respect it.
