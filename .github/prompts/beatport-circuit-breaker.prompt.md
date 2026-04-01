# beatport-circuit-breaker — Stop retrying after first auth failure

## Do not recreate existing files. Do not modify files not listed in scope.

## Problem

When the Beatport token is expired, the enrichment run emits 4 WARNING lines
per track (two 30-second timeout retries per track) before marking Beatport
unavailable. With 108 tracks this produces 432 WARNING lines and adds ~60s
of wasted timeout per track to the run time.

The correct behaviour: after the first 401 from Beatport, mark the provider
dead for the session and skip all subsequent Beatport requests instantly.

## Root cause

`tagslut/metadata/providers/beatport.py` catches 401/auth errors but does not
set a session-level dead flag. The retry logic in the HTTP client attempts a
token refresh on every request, timing out (30s) on each attempt.

## Scope of changes

### 1. `tagslut/metadata/providers/beatport.py`

Add a `_session_dead` instance flag (default `False`) to `BeatportProvider`.

In the methods that make authenticated requests (`search`, `search_by_isrc`,
or equivalent), check `self._session_dead` before attempting any network call:

```python
if self._session_dead:
    return []  # or raise ProviderAuthError with a clear message
```

When a 401 is caught or `BeatportAuthError` / token refresh failure occurs,
set `self._session_dead = True` and log once at WARNING level:

```
WARNING: beatport: token expired — skipping all further requests this session.
         Run 'tagslut auth refresh beatport' or get a fresh token from dj.beatport.com DevTools.
```

Do not retry after setting `_session_dead`. Do not log again on subsequent calls.

### 2. `tagslut/metadata/pipeline/runner.py` or `enricher.py` (whichever initialises providers)

No change needed — the dead flag lives on the provider instance which is
reused across all tracks in a single enrichment run.

## What NOT to change

- Do not modify the token refresh logic itself
- Do not modify the retry count or timeout values
- Do not modify any other provider
- Do not modify any migration, schema, or test fixtures

## Tests

Add or update `tests/metadata/test_beatport_provider_api.py`:

- Test that after a 401 response, `_session_dead` is `True`
- Test that a second call returns `[]` immediately without making any HTTP request
- Mock the HTTP layer — no real network calls

Run: `poetry run pytest tests/metadata/test_beatport_provider_api.py -v`

## Commit

```
git add -A
git commit -m "fix(beatport): circuit-breaker — skip all requests after first auth failure"
```
