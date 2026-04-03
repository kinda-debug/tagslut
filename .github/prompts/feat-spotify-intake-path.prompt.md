# feat(intake): accept Spotify URLs as intake input via song.link resolution

## Do not recreate existing files. Do not touch tools/get-intake interface.

## Context

Beatport → TIDAL direct playlist conversion (via TuneMyMusic or similar) has
unreliable track matching. Beatport → Spotify conversion is near-perfect. The
SpotiFLAC ecosystem proves that Spotify → TIDAL resolution via song.link/odesli
works reliably for electronic music catalog.

This prompt adds two things:

1. `tagslut get <spotify_url>` as a valid intake path. Internally it resolves the
   Spotify URL to a TIDAL ID via song.link, then proceeds through the normal tiddl
   download pipeline. No user-facing change to how intake works after this point.

2. A SpotiFLAC fallback: if tiddl download fails (auth error, token expired, track
   unavailable), attempt download via the `SpotiFLAC` Python package as a secondary
   acquisition path. Files acquired this way are flagged distinctly in provenance.

## Step 1 — Read existing code first

Before writing any code, read:
1. `tools/get-intake` and/or `tools/get` — understand how a TIDAL URL currently
   enters the pipeline and what the first intake steps are
2. The URL detection / dispatch logic that routes a URL to the correct provider
3. How `ingestion_method` and `ingestion_source` are set at intake time

## Step 2 — song.link resolver

Create `tagslut/intake/songlink.py` (new file).

```python
ODESLI_API = "https://api.song.link/v1-alpha.1/links"
REQUEST_DELAY = 6.5  # seconds — conservative for 10 req/min hard limit

def resolve_spotify_to_tidal(spotify_url: str) -> dict | None:
    """
    Resolve a Spotify track URL to platform IDs via song.link.
    Returns dict with keys: tidal_id, qobuz_id, isrc (all optional/None).
    Returns None if resolution fails or TIDAL entity absent.
    Caller responsible for REQUEST_DELAY between calls.
    """

def resolve_isrc_to_tidal(isrc: str) -> dict | None:
    """
    Resolve an ISRC directly to TIDAL/Qobuz IDs via song.link.
    Uses ?isrc={isrc}&platform=tidal endpoint.
    """
```


Implementation: GET `{ODESLI_API}?url={spotify_url}&platform=spotify`, parse
`entitiesByUniqueId`. Extract tidal_id from key starting with `"TIDAL_SONG::"`,
qobuz_id from `"QOBUZ_SONG::"`, isrc from any entity with `entity.get("isrc")`.
Log (do not raise) on non-critical failures.

## Step 3 — URL detection

In the URL routing / dispatch logic, add detection for Spotify track and playlist
URLs (patterns: `open.spotify.com/track/`, `open.spotify.com/album/`,
`open.spotify.com/playlist/`).

For a Spotify **track** URL:
- Call `resolve_spotify_to_tidal(url)`
- If `tidal_id` returned, construct `https://tidal.com/track/{tidal_id}` and hand
  off to the existing TIDAL intake path
- If resolution fails, raise `IntakeError`: "song.link could not resolve this
  Spotify URL to a TIDAL track"

For Spotify **album** or **playlist** URLs: raise `IntakeError` — not yet supported.
Do not silently do nothing.

## Step 4 — SpotiFLAC fallback

Add `SpotiFLAC` to `pyproject.toml` as an optional dependency:
```toml
[tool.poetry.extras]
fallback = ["SpotiFLAC"]
```
Do not add to the default dependency set. Log a clear warning if fallback is
triggered but SpotiFLAC is not installed.

Fallback trigger: in the tiddl download step, catch exceptions indicating auth
failure or track unavailability only. On those exceptions:

1. Log: `"tiddl download failed ({reason}), attempting SpotiFLAC fallback"`
2. Attempt:
```python
from SpotiFLAC import SpotiFLAC
SpotiFLAC(
    url=spotify_url,   # original Spotify URL — must be preserved through resolution
    output_dir=staging_dir,
    services=["tidal", "qobuz", "amazon"],
)
```
3. If succeeded, locate the downloaded file in `staging_dir` and continue pipeline
4. Set provenance: `ingestion_method='spotiflac_fallback'`,
   `ingestion_confidence='high'`, `ingestion_source=f'spotiflac:{spotify_url}'`

If no Spotify URL in the chain (user supplied TIDAL URL directly), log and re-raise
the original tiddl exception — fallback is unavailable.

## Step 5 — Tests

`tests/intake/test_songlink.py`:
- Mock odesli response; assert tidal_id, qobuz_id, isrc extracted correctly
- Mock response with no TIDAL entity; assert returns None, no exception
- Mock HTTP 429; assert returns None, no exception

`tests/intake/test_spotify_dispatch.py`:
- Mock resolution returning tidal_id; assert TIDAL URL constructed and dispatched
- Mock resolution returning None; assert IntakeError raised with clear message
- Spotify playlist URL; assert IntakeError raised immediately

## Commit sequence

```
feat(intake): add song.link resolver for spotify-to-tidal id crosswalk
feat(intake): accept spotify track urls as intake input
feat(intake): add spotiflac fallback acquisition on tiddl auth failure
docs(provenance): register spotiflac_fallback ingestion_method value
```
