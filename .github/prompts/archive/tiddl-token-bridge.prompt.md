# Prompt: tiddl → tokens.json bridge

**Agent**: Codex
**Section**: ROADMAP §20
**Status**: Ready to execute

---

## Goal

Fix the split auth state between tiddl and tagslut's TokenManager so that
`tagslut index enrich --providers tidal` does not print "tidal token expired"
warnings when tiddl has a live authenticated session.

## Problem statement

`TokenManager._load_tokens()` reads only from `~/.config/tagslut/tokens.json`.
`tiddl` stores its session — including `refresh_token` — separately in
`~/.tiddl/config.toml` under a `[token]` section.

These are completely independent auth states. A fresh tiddl session is invisible
to TagTokenManager. The result: tagslut fires token-missing or token-expired
warnings even when the operator's tiddl session is live and valid.

## Read first (in this order)

1. `tagslut/metadata/auth.py` — focus on `TokenManager._load_tokens()` and
   `TokenManager.get_token("tidal")`
2. `docs/TIDDL_CONFIG.md` — confirms tiddl config path and `[token]` section
3. `docs/CREDENTIAL_MANAGEMENT.md` — confirms `tokens.json` as source of truth
4. `~/.tiddl/config.toml` (runtime reference only, do not commit)

## tiddl config.toml token structure

The `[token]` section of `~/.tiddl/config.toml` contains at minimum:

```toml
[token]
access_token = "..."
refresh_token = "..."
expires_at = 1234567890   # Unix timestamp, may or may not be present
token_type = "Bearer"     # may or may not be present
```

The exact field names should be confirmed by reading the live file before
implementing. Do not assume field presence — all reads must be defensive.

The config file path is `~/.tiddl/config.toml` by default.
Respect the `TIDDL_CONFIG` environment variable as an override path if set.

## Implementation

### Where to add the fallback

`TokenManager._load_tokens()` in `tagslut/metadata/auth.py`.

After the existing `tokens.json` load, add a tidal-specific fallback block:

```python
def _try_import_tiddl_token(self) -> None:
    """
    Fallback: if tokens.json has no usable tidal refresh_token, attempt to
    import one from ~/.tiddl/config.toml (or $TIDDL_CONFIG override).

    Writes the imported token into tokens.json so future reads are self-healing.
    Does nothing and logs at DEBUG level on any failure — never raises.
    """
```

Call `_try_import_tiddl_token()` at the end of `_load_tokens()`, but only
when the tidal section is absent or has an empty/missing `refresh_token`.

### Exact trigger condition

Import from tiddl config if and only if:
```python
tidal_data = self._tokens.get("tidal", {})
has_refresh = bool(tidal_data.get("refresh_token"))
# Only import if no usable refresh token in tokens.json
```

If `tokens.json` already has a valid tidal `refresh_token`, skip the import
entirely. Do not overwrite a working token.

### Import logic

1. Resolve config path: `Path(os.getenv("TIDDL_CONFIG", "~/.tiddl/config.toml")).expanduser()`
2. If the file does not exist: log at DEBUG, return silently.
3. Parse with `tomllib` (Python 3.11+ stdlib) or `tomli` as fallback.
   Do not add `tomli` as a new dependency if `tomllib` is available.
4. Extract `[token]` section. If missing: log at DEBUG, return.
5. Read `refresh_token` (required), `access_token` (optional),
   `expires_at` (optional, convert to float), `token_type` (optional).
6. If `refresh_token` is empty or absent: log at DEBUG, return.
7. Call `self.set_token("tidal", access_token=..., refresh_token=..., ...)`.
   - If `access_token` is absent from tiddl config, use empty string `""`.
     TokenManager will trigger a refresh on first API call.
8. Log at INFO: `"Imported tidal refresh_token from tiddl config; tokens.json updated"`

### Self-healing write

`set_token()` already calls `_save_tokens()`. The imported token is persisted
to `tokens.json` on first successful import. Subsequent runs will find it
there and skip the tiddl fallback entirely.

### Error handling

Every step in `_try_import_tiddl_token` must be wrapped in a broad try/except.
A missing file, a malformed TOML, a missing key, or a write failure must all
result in a DEBUG log and silent return — never an exception propagating to
the caller. The enrichment pipeline must not break because of a tiddl config
parse failure.

## What not to change

- Do not modify the tiddl config file. Read only.
- Do not change the `tokens.json` schema.
- Do not change `_load_tokens()` behavior for Beatport or any other provider.
- Do not change any CLI command interfaces.
- Do not add new dependencies to `pyproject.toml` unless `tomllib` is
  genuinely unavailable (Python < 3.11). In that case, add `tomli` and
  update `pyproject.toml`.

## Verification

```bash
# 1. Confirm tiddl has a live session
cat ~/.tiddl/config.toml | grep refresh_token

# 2. Clear tidal from tokens.json to simulate the split-auth state
python3 -c "
import json, pathlib
p = pathlib.Path('~/.config/tagslut/tokens.json').expanduser()
d = json.loads(p.read_text())
d.pop('tidal', None)
p.write_text(json.dumps(d, indent=2))
print('tidal section removed')
"

# 3. Run enrich dry-run — must NOT print 'tidal token expired' or 'no tidal token'
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python -c "
from tagslut.metadata.auth import TokenManager
tm = TokenManager()
tok = tm.get_token('tidal')
print('token present:', tok is not None)
print('has refresh:', bool(tok and tok.refresh_token))
"

# 4. Confirm tokens.json now has tidal section (self-healing write)
python3 -c "
import json, pathlib
p = pathlib.Path('~/.config/tagslut/tokens.json').expanduser()
d = json.loads(p.read_text())
print('tidal section present:', 'tidal' in d)
print('refresh_token present:', bool(d.get('tidal', {}).get('refresh_token')))
"
```

## Tests required

File: `tests/metadata/test_tiddl_token_bridge.py`

1. **No tiddl config** — `_try_import_tiddl_token` returns silently when
   `~/.tiddl/config.toml` does not exist.
2. **Malformed TOML** — returns silently, does not raise.
3. **Missing `[token]` section** — returns silently.
4. **Empty `refresh_token`** — returns silently, does not write.
5. **Valid tiddl token, no tidal in tokens.json** — imports refresh_token,
   writes to tokens.json, subsequent `get_token("tidal")` returns non-None.
6. **Existing tidal refresh_token in tokens.json** — tiddl config is NOT read
   (verify by asserting no file access via mock or by using a non-existent path).
7. **TIDDL_CONFIG env var** — fallback uses the overridden path when set.

Use `tmp_path` fixtures for all file I/O. Do not touch real `~/.tiddl` or
`~/.config/tagslut` in tests.

## Done when

`poetry run pytest tests/metadata/test_tiddl_token_bridge.py -v` — all pass.

Running the verification block above shows `token present: True` and
`refresh_token present: True` after clearing tidal from tokens.json, confirming
the bridge fired and self-healed.

`tagslut index enrich --providers tidal --dry-run` produces no token warning
when `~/.tiddl/config.toml` has a live session.

## Commit message

```
fix(auth): fallback tidal refresh_token from tiddl config.toml
```
