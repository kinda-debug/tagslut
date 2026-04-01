# tidal-auth-unification — Fix tagslut auth login tidal to delegate to tiddl

## Do not recreate existing files. Do not modify files not listed in scope.

## Context

`tagslut auth login tidal` attempts a device authorization flow using the
Android app client_id (`zU4XHVVkc2tDPo4t`). This returns 400 from TIDAL's
auth endpoint. The only working TIDAL auth path is `tiddl auth refresh`.

The correct fix is: `tagslut auth login tidal` delegates to tiddl via
subprocess, then syncs the resulting token into `tokens.json` via the
existing `TokenManager.sync_from_tiddl()` method.

`tagslut auth refresh tidal` should do the same — run `tiddl auth refresh`
then sync.

## Scope of changes

### 1. `tagslut/cli/commands/auth.py`

Replace the `tidal` branch in `auth_login` with:

```python
if provider == 'tidal':
    import subprocess
    click.echo("Delegating to tiddl for TIDAL authentication...")
    result = subprocess.run(["tiddl", "auth", "login"], check=False)
    if result.returncode != 0:
        click.echo("tiddl auth login failed. Is tiddl installed and configured?", err=True)
        raise SystemExit(1)
    token = token_manager.sync_from_tiddl()
    if token:
        click.echo("TIDAL token synced from tiddl successfully.")
    else:
        click.echo("Warning: tiddl login succeeded but token sync failed. Check ~/.tiddl/auth.json", err=True)
```

Replace the `tidal` branch in `auth_refresh` with:

```python
elif provider == 'tidal':
    import subprocess
    result = subprocess.run(["tiddl", "auth", "refresh"], check=False)
    if result.returncode != 0:
        click.echo("tiddl auth refresh failed.", err=True)
        raise SystemExit(1)
    token = token_manager.sync_from_tiddl()
    if token:
        import time
        click.echo(f"TIDAL token refreshed and synced (expires: {time.ctime(token.expires_at)})")
    else:
        click.echo("Warning: refresh succeeded but sync failed.", err=True)
```

### 2. `tagslut/metadata/auth.py`

Remove `start_tidal_device_auth` and `complete_tidal_device_auth` methods —
they are dead code now that auth delegates to tiddl. Do not remove anything else.

Remove `TIDAL_CLIENT_ID` and `TIDAL_CLIENT_SECRET` constants and their
`_get_tidal_credentials()` helper — also dead code. Verify nothing else
references them before removing.

### 3. `tools/auth`

The `refresh_tidal` function currently calls `tiddl auth refresh` directly —
this is already correct. No change needed there.

## What NOT to change

- Do not modify `sync_from_tiddl()` — it already works correctly
- Do not modify `refresh_tidal_token()` — keep it as a fallback for programmatic use
- Do not modify any migration, schema, or test fixtures
- Do not remove `logout_tidal()` — it is used by `auth logout tidal`

## Tests

Update `tests/metadata/test_auth.py` if it tests device auth flows:
- Replace any test that calls `start_tidal_device_auth` / `complete_tidal_device_auth`
  with a test that mocks `subprocess.run` and verifies `sync_from_tiddl` is called

Run: `poetry run pytest tests/ -k "auth" -v`

## Commit

```
git add -A
git commit -m "fix(auth): delegate tagslut auth login/refresh tidal to tiddl subprocess"
```
