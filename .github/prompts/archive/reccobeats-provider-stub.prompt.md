# Prompt: ReccoBeats provider stub

**Agent**: Codex
**Section**: ROADMAP §22
**Status**: Ready to execute

**COMMIT ALL CHANGES BEFORE EXITING.**

---

## Goal

Implement `ReccoBeatsProvider` — a metadata provider that fetches Spotify-style audio
features (energy, danceability, valence, acousticness, instrumentalness, loudness, tempo)
via the ReccoBeats public API and writes them into `EnrichmentResult` canonical fields
that are currently never populated.

ReccoBeats is a free, open API requiring no account registration or API key for basic use.

---

## Read first (in this order)

1. `tagslut/metadata/models/types.py` — `EnrichmentResult` audio feature fields
2. `tagslut/metadata/providers/base.py` — `AbstractProvider`, `ProviderTrack`, `RateLimitConfig`
3. `tagslut/metadata/providers/qobuz.py` — most recent provider scaffold, use as structural template
4. `tagslut/metadata/provider_registry.py` — `PROVIDER_REGISTRY`, `ProviderPolicy`, `ProviderActivationConfig`
5. `tagslut/metadata/capabilities.py` — `Capability` enum
6. `tagslut/metadata/metadata_router.py` — capability availability rules
7. `tagslut/metadata/pipeline/stages.py` — where canonical fields are assembled from provider results
8. `tagslut/metadata/store/db_writer.py` — confirm audio feature fields are written to DB

---

## API facts (validated — do not guess)

**Base URL**: `https://api.reccobeats.com/v1`
**Auth**: None required for either endpoint. No API key, no registration.

### Step 1 — resolve ISRC → internal track ID

```
GET /v1/track?ids={isrc}
```

Response: `{"content": [{"id": "<uuid>", "isrc": "<isrc>", "trackTitle": "...", ...}, ...]}`

- `ids` is the ISRC string (despite the parameter name suggesting a list, single ISRC works).
- Response may return multiple entries for the same ISRC (different regional releases).
- Use the first entry with a matching ISRC in `content[].isrc`.
- The `id` field is a UUID — this is the ReccoBeats internal track ID.

### Step 2 — fetch audio features by internal ID

```
GET /v1/audio-features?ids={reccobeats_uuid}
```

Response:
```json
{
  "content": [{
    "id": "c00cbf4f-...",
    "isrc": "USRC17607839",
    "acousticness": 0.204,
    "danceability": 0.595,
    "energy": 0.847,
    "instrumentalness": 0.0,
    "key": 0,
    "liveness": 0.17,
    "loudness": -7.934,
    "mode": 1,
    "speechiness": 0.288,
    "tempo": 150.343,
    "valence": 0.546
  }]
}
```

- `tempo` maps to BPM. Use only if `EnrichmentResult.canonical_bpm` is None (do not
  overwrite Beatport BPM with ReccoBeats tempo — Beatport is the authoritative BPM source).
- All float fields are 0.0–1.0 except `loudness` (negative dB) and `tempo` (BPM).

### Rate limiting

No documented rate limit. Use a conservative 0.3s delay between requests.
Implement using `RateLimitConfig` from `base.py` as other providers do.

---

## Implementation

### New file: `tagslut/metadata/providers/reccobeats.py`

```python
class ReccoBeatsProvider(AbstractProvider):
    """
    ReccoBeats audio feature provider.

    Two-step lookup:
    1. /v1/track?ids={isrc}  → resolve ISRC to internal UUID
    2. /v1/audio-features?ids={uuid} → fetch audio features

    No auth required. Free public API.
    """

    BASE_URL = "https://api.reccobeats.com/v1"
    PROVIDER_NAME = "reccobeats"

    capabilities = {
        Capability.METADATA_FETCH_TRACK_BY_ID,   # treat "by ID" as "by ISRC"
        Capability.METADATA_SEARCH_BY_ISRC,
    }
```

Implement:
- `fetch_by_isrc(isrc: str) -> Optional[ProviderTrack]`
  1. GET `/v1/track?ids={isrc}`
  2. Find first `content[]` entry where `entry["isrc"] == isrc`
  3. If none found: return None
  4. GET `/v1/audio-features?ids={entry["id"]}`
  5. Find first `content[]` entry where `entry["id"] == track_id`
  6. Map fields to `ProviderTrack` (see mapping below)

- `search(query: str, ...) -> list[ProviderTrack]`
  ReccoBeats has no text search endpoint. Implement as a stub that returns `[]` and
  logs at DEBUG. Do not raise — the router will handle capability filtering.

- `close() -> None` — close the httpx session.

**ProviderTrack field mapping:**

| ReccoBeats field | ProviderTrack field | Notes |
|---|---|---|
| `acousticness` | `acousticness` | Add field if not present |
| `danceability` | `danceability` | |
| `energy` | `energy` | |
| `instrumentalness` | `instrumentalness` | |
| `loudness` | `loudness` | |
| `valence` | `valence` | |
| `tempo` | `bpm` | Only populate if no BPM from higher-priority source |
| `isrc` | `isrc` | From step 1 response |

If `ProviderTrack` does not have audio feature fields, add them as `Optional[float] = None`
fields. Do not add fields that don't exist in `EnrichmentResult`.

### Cascade rule in `stages.py`

After existing provider cascade, add a ReccoBeats enrichment pass:

```python
# Audio features from ReccoBeats (lowest priority — fills never-populated fields only)
if reccobeats_result:
    if result.canonical_energy is None:
        result.canonical_energy = reccobeats_result.energy
    if result.canonical_danceability is None:
        result.canonical_danceability = reccobeats_result.danceability
    if result.canonical_valence is None:
        result.canonical_valence = reccobeats_result.valence
    if result.canonical_acousticness is None:
        result.canonical_acousticness = reccobeats_result.acousticness
    if result.canonical_instrumentalness is None:
        result.canonical_instrumentalness = reccobeats_result.instrumentalness
    if result.canonical_loudness is None:
        result.canonical_loudness = reccobeats_result.loudness
    # BPM: only use ReccoBeats tempo if no BPM from authoritative sources
    if result.canonical_bpm is None and reccobeats_result.bpm:
        result.canonical_bpm = reccobeats_result.bpm
```

### Registry

Add to `PROVIDER_REGISTRY` in `provider_registry.py`:
```python
"reccobeats": ReccoBeatsProvider,
```

Add to `ProviderActivationConfig`:
```python
reccobeats: ProviderPolicy = ProviderPolicy(
    metadata_enabled=True,   # on by default — no auth required
    download_enabled=False,
    trust="secondary",       # audio features only, not identity-authoritative
)
```

Add parsing in `load_provider_activation_config`.
Add `reccobeats` branch in `resolve_provider_status` in `provider_state.py`.

### Capability routing

In `metadata_router.py`, add ReccoBeats capability availability rules:
- `METADATA_SEARCH_BY_ISRC`: available when `metadata_enabled=True` (no auth required)
- `METADATA_FETCH_TRACK_BY_ID`: same
- `METADATA_SEARCH_BY_TEXT`: not supported (stub returns `[]`)

ReccoBeats should be appended after Beatport and TIDAL in the default provider list,
not prepended. It is a supplementary source, not a primary one.

Default `ENRICH_PROVIDERS` in `tools/get-intake` should NOT be changed — ReccoBeats
runs as an additive pass, not a replacement for primary providers.

### Export from `__init__.py`

Add `ReccoBeatsProvider` to `tagslut/metadata/providers/__init__.py` exports.

---

## What NOT to change

- `tools/get-intake` ENRICH_PROVIDERS default
- Any existing provider implementations
- DB schema or migrations (columns already exist in `storage/schema.py`)
- `EnrichmentResult` field names (already correct)
- Identity service

---

## Verification

```bash
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"

# 1. Compile check
poetry run python -m compileall tagslut -q

# 2. Live API smoke test
poetry run python3 -c "
from tagslut.metadata.providers.reccobeats import ReccoBeatsProvider
from tagslut.metadata.auth import TokenManager
p = ReccoBeatsProvider(TokenManager())
result = p.fetch_by_isrc('USRC17607839')
print('result:', result)
assert result is not None, 'Expected a result for known ISRC'
assert result.energy is not None, 'Expected energy field'
assert result.danceability is not None, 'Expected danceability field'
print('energy:', result.energy)
print('danceability:', result.danceability)
print('valence:', result.valence)
p.close()
print('PASS')
"

# 3. Registry smoke test
poetry run python3 -c "
from tagslut.metadata.provider_registry import ProviderActivationConfig
cfg = ProviderActivationConfig()
print('reccobeats metadata_enabled:', cfg.reccobeats.metadata_enabled)
print('reccobeats trust:', cfg.reccobeats.trust)
assert cfg.reccobeats.metadata_enabled is True
assert cfg.reccobeats.trust == 'secondary'
print('PASS')
"

# 4. Targeted tests
poetry run pytest tests/metadata/test_reccobeats_provider.py -v
```

---

## Tests required

File: `tests/metadata/test_reccobeats_provider.py`

1. `test_fetch_by_isrc_returns_audio_features` — mock HTTP, assert energy/danceability/valence populated.
2. `test_fetch_by_isrc_returns_none_when_isrc_not_found` — empty `content[]`, assert None returned.
3. `test_search_returns_empty_list` — stub, assert `[]` without raising.
4. `test_reccobeats_registered_in_registry` — assert `"reccobeats"` in `PROVIDER_REGISTRY`.
5. `test_reccobeats_enabled_by_default` — `ProviderActivationConfig()` has `reccobeats.metadata_enabled = True`.
6. `test_bpm_not_overwritten_by_reccobeats_tempo` — if `canonical_bpm` already set, ReccoBeats tempo does not overwrite.
7. `test_audio_features_cascade_fills_empty_fields` — assert cascade rule populates `canonical_energy` etc. when None.

Use `tmp_path` and mock HTTP — do not make live API calls in tests.

---

## Done when

`poetry run pytest tests/metadata/test_reccobeats_provider.py -v` — all pass.

Live smoke test (`fetch_by_isrc('USRC17607839')`) returns non-None with populated
`energy`, `danceability`, `valence` fields.

`tagslut provider status` lists `reccobeats` as `metadata_enabled=true`.

---

## Commit message

```
feat(reccobeats): add audio feature provider using ReccoBeats public API
```
