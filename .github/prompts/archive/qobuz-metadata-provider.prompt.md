# qobuz-metadata-provider — Implement Qobuz as a real metadata provider

## Do not recreate existing files. Do not modify files not listed in scope.

## Context

`tagslut/metadata/providers/qobuz.py` is currently a stub — `fetch_by_id` and
`search` both return None/[]. This prompt implements the Qobuz metadata provider
fully so it can be used as a third provider in the enrichment chain after
`beatport → tidal → qobuz`.

Qobuz does not offer a public self-service API. Credentials must be extracted
dynamically from the Qobuz web player JavaScript bundle at runtime. This is the
same approach used by streamrip, qobuz-dl, and other open-source tools.

## Architecture overview

### Credential acquisition (runtime extraction)

Qobuz requires two app-level credentials:
- `app_id` — extracted from `play.qobuz.com` bundle.js via regex
- `app_secret` — extracted from bundle.js via seed/timezone pattern and base64 decode

These are NOT user secrets. They are embedded in Qobuz's public JavaScript and
change when Qobuz deploys. They must be re-extracted periodically.

After obtaining `app_id` + `app_secret`, the user must authenticate with their
Qobuz email and MD5-hashed password to obtain a `user_auth_token`.

### Auth storage in tokens.json

```json
{
  "qobuz": {
    "app_id": "...",
    "app_secret": "...",
    "user_auth_token": "...",
    "user_id": "..."
  }
}
```

### API base URL

`https://www.qobuz.com/api.json/0.2/`

All requests require `app_id` as a query parameter and authenticated requests
require `X-User-Auth-Token` header.

## Scope of changes

### 1. New file: `tagslut/metadata/qobuz_credential_extractor.py`

Implement credential extraction from Qobuz web player:

```python
import re
import requests
from base64 import b64decode
from typing import Optional, Dict

QOBUZ_WEB_URL = "https://play.qobuz.com"
_BUNDLE_URL_REGEX = r'src="([^"]+bundle\.js)"'
_APP_ID_REGEX = r'["\']?app_id["\']?\s*:\s*["\'](\d+)["\']'
_SEED_TIMEZONE_REGEX = r'initialSeed\("([^"]+)",window\.utimezone\.([a-z_]+)\)'

def extract_qobuz_credentials() -> Dict[str, str]:
    """
    Extract app_id and app_secret from Qobuz web player bundle.js.

    Returns dict with keys: app_id, app_secret (first valid secret found).
    Raises RuntimeError if extraction fails.
    """
```

Steps:
1. GET `https://play.qobuz.com`, find bundle.js URL via `_BUNDLE_URL_REGEX`
2. GET bundle.js
3. Extract `app_id` via `_APP_ID_REGEX`
4. Find all `(seed, timezone)` pairs via `_SEED_TIMEZONE_REGEX`
5. For each seed: `b64decode(seed.encode()).decode('utf-8')` → candidate secret
6. Return `{"app_id": app_id, "app_secret": first_valid_secret}`

Use `requests` (not httpx) for simplicity. Add 1.0s User-Agent:
`Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0`

### 2. `tagslut/metadata/auth.py`

Add Qobuz auth methods to `TokenManager`:

```python
def get_qobuz_app_credentials(self) -> tuple[Optional[str], Optional[str]]:
    """Return (app_id, app_secret) from tokens.json qobuz section."""

def set_qobuz_credentials(
    self,
    app_id: str,
    app_secret: str,
    user_auth_token: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    """Store Qobuz credentials in tokens.json."""

def login_qobuz(self, email: str, password_md5: str) -> Optional[str]:
    """
    Authenticate with Qobuz using email and MD5-hashed password.
    Stores user_auth_token in tokens.json. Returns the token or None.

    POST https://www.qobuz.com/api.json/0.2/user/login
    params: app_id, email, password (MD5 hash)
    response: {"user": {"auth_token": "...", "id": "..."}}
    """

def ensure_qobuz_token(self) -> Optional[str]:
    """
    Return valid Qobuz user_auth_token or None.
    Does not auto-refresh (Qobuz tokens are long-lived).
    """
```

Do NOT add `qobuz` to `ensure_valid_token` — Qobuz uses a different auth model
(no OAuth, no refresh token). Keep the existing `ensure_valid_token` unchanged.

### 3. `tagslut/metadata/providers/qobuz.py`

Replace the stub with a full implementation:

```python
class QobuzProvider(AbstractProvider):
    name = "qobuz"
    supports_isrc_search = True
    capabilities = {
        Capability.METADATA_FETCH_TRACK_BY_ID,
        Capability.METADATA_SEARCH_BY_ISRC,
        Capability.METADATA_SEARCH_BY_TEXT,
        Capability.METADATA_FETCH_ARTWORK,
    }
    rate_limit_config = RateLimitConfig(min_delay=0.5, max_retries=3)
    BASE_URL = "https://www.qobuz.com/api.json/0.2"
```

`_get_default_headers`:
- `X-App-Id: {app_id}` from token_manager
- `X-User-Auth-Token: {user_auth_token}` from token_manager

`fetch_by_id(track_id)`:
- GET `{BASE_URL}/track/get?track_id={track_id}&app_id={app_id}`
- Parse response into `ProviderTrack`

`search_by_isrc(isrc)`:
- GET `{BASE_URL}/track/search?query={isrc}&app_id={app_id}&limit=5`
- Filter results where `item["isrc"] == isrc`
- Return with `MatchConfidence.EXACT`

`search(query, limit=10)`:
- GET `{BASE_URL}/track/search?query={query}&app_id={app_id}&limit={limit}`
- Parse `response["tracks"]["items"]` list

`_normalize_track(raw)` — map Qobuz fields to `ProviderTrack`:

| Qobuz field | ProviderTrack field |
|---|---|
| `id` | `service_track_id` |
| `title` | `title` |
| `performer.name` or `artist.name` | `artist` |
| `album.title` | `album` |
| `album.id` | `album_id` |
| `isrc` | `isrc` |
| `duration` (seconds int) | `duration_ms` (× 1000) |
| `track_number` | `track_number` |
| `album.release_date_original` | `release_date` |
| `album.label.name` | `label` |
| `version` | `version` |
| `parental_warning` | `explicit` |
| `album.image.large` | `album_art_url` |
| `composer.name` | `composer` |
| `work` | (store in `raw`, not in ProviderTrack — no field exists) |

Set `service = "qobuz"`. Set `url = f"https://open.qobuz.com/track/{id}"`.

### 4. `tagslut/cli/commands/auth.py` (or wherever auth CLI lives)

Add `tagslut auth login qobuz` command:

```
tagslut auth login qobuz --email EMAIL [--password PASSWORD]
```

Steps:
1. If `--password` not provided, prompt securely (use `click.prompt(..., hide_input=True)`)
2. MD5-hash the password: `hashlib.md5(password.encode()).hexdigest()`
3. Extract credentials: `extract_qobuz_credentials()` (prints progress)
4. Store `app_id` + `app_secret` via `token_manager.set_qobuz_credentials()`
5. Login: `token_manager.login_qobuz(email, password_md5)`
6. Print success with token prefix

Add `tagslut auth status` output for qobuz: show configured/not configured,
has token or not.

### 5. `tagslut/cli/commands/index.py`

Change default providers from `'beatport,tidal'` to `'beatport,tidal,qobuz'`
at line ~1007 (`default='beatport,tidal'`).

## What NOT to change

- Do not modify `ProviderTrack` dataclass fields
- Do not modify `EnrichmentStats`
- Do not modify the enrichment runner or orchestrator
- Do not modify any migration files
- Do not touch the TIDAL or Beatport providers

## Error handling

- If `app_id` or `app_secret` extraction fails: raise `RuntimeError` with clear message
- If Qobuz login returns non-200: log error, return None (do not raise)
- If `user_auth_token` missing at request time: log warning, return [] / None gracefully
- `InvalidAppSecretError` in response body (400 status): log and return None

## Tests

Add `tests/metadata/providers/test_qobuz_provider.py`:
- Test `_normalize_track` maps fields correctly
- Test `search_by_isrc` filters by ISRC
- Test missing `user_auth_token` returns empty results gracefully
- Mock HTTP responses with `unittest.mock`

Add `tests/metadata/test_qobuz_credential_extractor.py`:
- Test `extract_qobuz_credentials` parses app_id and app_secret from mock HTML/JS
- Mock HTTP responses

Run: `poetry run pytest tests/metadata/providers/test_qobuz_provider.py tests/metadata/test_qobuz_credential_extractor.py -v`

## Commit

```
git add -A
git commit -m "feat(providers): implement Qobuz metadata provider with credential extraction and auth"
```
