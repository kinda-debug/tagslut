# auth-tidal-logout

Add `tagslut auth logout <provider>` and harden `auth login` to match
tiddl's login/logout/refresh UX.

## Context

- Auth infrastructure: `tagslut/metadata/auth.py` (`TokenManager`)
- CLI commands: `tagslut/cli/commands/auth.py`
- Login helpers: `tagslut/cli/commands/_auth_helpers.py`
- tiddl reference: device-auth flow, server-side logout, early-exit guard on login

## Scope

Three changes, all surgical. No new files. No schema changes.

---

## Change 1 — `TokenManager.logout_tidal()` in `tagslut/metadata/auth.py`

Add this method to `TokenManager` after `refresh_tidal_token`:

```python
def logout_tidal(self) -> None:
    """
    Revoke the Tidal access token server-side, then clear locally.

    Mirrors tiddl's logout behaviour. Best-effort: if the revocation
    request fails (network error, already-expired token), we still
    clear the local token so the user is not stuck.
    """
    access_token = (self._tokens.get("tidal") or {}).get("access_token")
    if access_token:
        try:
            import httpx
            response = httpx.post(
                "https://api.tidal.com/v1/logout",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            if response.status_code not in (200, 204):
                logger.warning(
                    "Tidal server-side logout returned %d; clearing locally anyway",
                    response.status_code,
                )
        except Exception as e:
            logger.warning("Tidal server-side logout failed (%s); clearing locally", e)

    # Always clear local token regardless of server result
    if "tidal" in self._tokens:
        self._tokens["tidal"].pop("access_token", None)
        self._tokens["tidal"].pop("refresh_token", None)
        self._tokens["tidal"].pop("expires_at", None)
        self._save_tokens()
    logger.info("Tidal token cleared")
```

---

## Change 2 — `auth logout` command in `tagslut/cli/commands/auth.py`

Add inside `register_auth_group`, after the `auth refresh` command block:

```python
@auth.command("logout")
@click.argument("provider")
@click.option("--tokens-path", type=click.Path(), help="Path to tokens.json")
def auth_logout(provider, tokens_path):
    """
    Logout and remove stored credentials for a provider.

    For tidal: revokes the access token server-side, then clears locally.
    For beatport: clears the locally stored token only (no server-side revocation).
    """
    from tagslut.metadata.auth import DEFAULT_TOKENS_PATH, TokenManager

    if provider not in {"tidal", "beatport"}:
        click.echo(f"Error: Unsupported provider '{provider}'. Use tidal or beatport.", err=True)
        raise SystemExit(1)

    path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
    token_manager = TokenManager(path)

    if provider == "tidal":
        click.echo("Logging out of Tidal...")
        token_manager.logout_tidal()
        click.echo("Logged out.")

    elif provider == "beatport":
        # Beatport tokens are manually obtained; just clear locally
        token_manager.set_token("beatport", access_token="", refresh_token=None, expires_at=None)
        click.echo("Beatport token cleared.")
```

---

## Change 3 — early-exit guard in `auth login` for already-authenticated state

In `tagslut/cli/commands/auth.py`, inside the `auth_login` command, at the
top of each provider branch, add a guard that exits early if a valid
non-expired token is already present. Mirrors tiddl's "Already logged in."
behaviour.

Replace the current `auth_login` command body with:

```python
@auth.command("login")
@click.argument("provider")
@click.option("--tokens-path", type=click.Path(), help="Path to tokens.json")
@click.option("--force", "-f", is_flag=True, help="Re-authenticate even if already logged in.")
def auth_login(provider, tokens_path, force):
    """
    Authenticate with a provider interactively.

    Supported providers:
    - tidal: Device authorization (opens browser)
    - beatport: Manual token from browser DevTools

    Use --force to re-authenticate even when a valid token already exists.
    """
    from tagslut.metadata.auth import DEFAULT_TOKENS_PATH, TokenManager

    if provider not in {"tidal", "beatport"}:
        click.echo(f"Error: Unsupported provider '{provider}'. Use tidal or beatport.", err=True)
        raise SystemExit(1)

    path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
    token_manager = TokenManager(path)

    if not force:
        token = token_manager.get_token(provider)
        if token and token.access_token and not token.is_expired:
            click.echo(f"Already logged in to {provider}. Use --force to re-authenticate.")
            return

    if provider == "tidal":
        _tidal_device_login(token_manager)
    elif provider == "beatport":
        _beatport_token_input(token_manager)
```

---

## Constraints

- Use `edit_block` / `str_replace` for all edits. Do NOT rewrite entire files.
- `logout_tidal()` must always clear locally even if the HTTP call fails.
- `logout beatport` must not attempt any network call — just clear the stored token.
- Do not add any new Python dependencies.
- Do not touch anything outside `tagslut/metadata/auth.py`, `tagslut/cli/commands/auth.py`,
  and `tagslut/cli/commands/_auth_helpers.py`.
- Targeted pytest only:
  ```
  poetry run pytest tests/ -k "auth" -v
  ```

## Commit

```
feat(auth): add logout command and login early-exit guard
```

Single commit covering all three changes.
