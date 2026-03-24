from __future__ import annotations

import time
from pathlib import Path

import click

from tagslut.cli.commands._auth_helpers import (
    _beatport_token_input,
    _tidal_device_login,
)


def _emit_provider_token(provider: str, tokens_path: str | None) -> None:
    from tagslut.metadata.auth import DEFAULT_TOKENS_PATH, TokenManager

    if provider not in {"beatport", "tidal"}:
        click.echo(f"Error: Unsupported provider '{provider}'. Use beatport or tidal.", err=True)
        raise SystemExit(1)

    path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
    token_manager = TokenManager(path)
    token = token_manager.ensure_valid_token(provider)

    if token and token.access_token and not token.is_expired:
        click.echo(token.access_token)
        return

    provider_name = "Beatport" if provider == "beatport" else "Tidal"
    click.echo(
        f"Error: No valid {provider_name} token. Run 'tagslut auth login {provider}'.",
        err=True,
    )
    raise SystemExit(1)


def register_auth_group(cli: click.Group) -> None:
    @cli.group()
    def auth():  # type: ignore  # TODO: mypy-strict
        """Canonical provider authentication commands."""

    @cli.command("token-get")
    @click.argument("provider")
    @click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
    def token_get(provider, tokens_path):  # type: ignore  # TODO: mypy-strict
        """
        Print only the access token for a provider.

        Intended for shell capture, for example:
          BEATPORT_ACCESS_TOKEN=$(tagslut token-get beatport)
        """
        _emit_provider_token(provider, tokens_path)

    @auth.command("status")
    @click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
    @click.option('--no-refresh', is_flag=True, help='Skip auto-refresh of tokens')
    def auth_status(tokens_path, no_refresh):  # type: ignore  # TODO: mypy-strict
        """
        Show authentication status for all providers.

        Displays which providers are configured and whether their tokens
        are valid or expired. Automatically refreshes tokens for providers
        that support it.
        """
        from tagslut.metadata.auth import DEFAULT_TOKENS_PATH, TokenManager

        path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
        token_manager = TokenManager(path)

        click.echo(f"\nTokens file: {path}")
        click.echo("=" * 60)

        # Auto-refresh tokens for providers that support it
        if not no_refresh:
            # Beatport - client credentials
            if token_manager.is_configured("beatport"):
                token = token_manager.get_token("beatport")
                if token is None or token.is_expired:
                    click.echo("Refreshing Beatport token...")
                    token_manager.refresh_beatport_token()

            # Tidal - refresh token (only if already authenticated)
            if token_manager.is_configured("tidal"):
                token = token_manager.get_token("tidal")
                if token is None or token.is_expired:
                    click.echo("Refreshing Tidal token...")
                    token_manager.refresh_tidal_token()

        status = token_manager.status()

        for provider, info in status.items():
            configured = "✓" if info.get('configured') else "✗"
            has_token = "✓" if info.get('has_token') else "✗"

            if provider == "itunes":
                token_status = "ready (no auth needed)"
            elif info.get('expired') is True:
                token_status = "EXPIRED"
            elif info.get('has_token'):
                token_status = "valid"
            else:
                token_status = "not authenticated"

            click.echo(f"{provider:12} | {configured} configured | {has_token} token ({token_status})")

        # Show help for unconfigured providers
        click.echo("")
        unconfigured = [p for p, info in status.items() if not info.get('configured')]
        if unconfigured:
            click.echo("To configure providers:")
            if 'beatport' in unconfigured:
                click.echo("  beatport: Run 'tagslut auth login beatport'")
                click.echo("            (paste token from dj.beatport.com DevTools)")
            if 'tidal' in unconfigured:
                click.echo("  tidal:    Run 'tagslut auth login tidal'")

    @auth.command("init")
    @click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
    def auth_init(tokens_path):  # type: ignore  # TODO: mypy-strict
        """
        Initialize tokens.json with template structure.

        Creates a new tokens.json file with placeholders for all supported
        providers. You'll need to fill in your API credentials.
        """
        from tagslut.metadata.auth import DEFAULT_TOKENS_PATH, TokenManager

        path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
        token_manager = TokenManager(path)
        token_manager.init_template()

        click.echo(f"Created tokens template at: {path}")
        click.echo("\nNext steps:")
        click.echo("  1. Beatport: Edit tokens.json to add client_id and client_secret")
        click.echo("  2. Tidal: Run 'tagslut auth login tidal'")

    @auth.command("refresh")
    @click.argument('provider')
    @click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
    def auth_refresh(provider, tokens_path):  # type: ignore  # TODO: mypy-strict
        """
        Refresh access token for a provider.

        Supports automatic refresh for:
        - beatport (client credentials)
        - tidal (refresh token, requires prior auth-login)
        """
        from tagslut.metadata.auth import DEFAULT_TOKENS_PATH, TokenManager

        path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
        token_manager = TokenManager(path)

        if provider == 'beatport':
            token = token_manager.refresh_beatport_token()
            if token and not token.is_expired:
                click.echo(f"Beatport token valid until: {time.ctime(token.expires_at)}")
            else:
                click.echo("Beatport token expired or missing.")
                click.echo("Run 'tagslut auth login beatport' to set a new token.")

        elif provider == 'tidal':
            click.echo("Refreshing Tidal token...")
            token = token_manager.refresh_tidal_token()
            if token:
                click.echo(f"Success! Token expires at: {time.ctime(token.expires_at)}")
            else:
                click.echo("Failed. Run 'tagslut auth login tidal' first.")

        else:
            click.echo(f"Unknown provider: {provider}")

    @auth.command("token-get")
    @click.argument("provider")
    @click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
    def auth_token_get(provider, tokens_path):  # type: ignore  # TODO: mypy-strict
        """
        Print only the access token for a provider.

        Intended for shell capture, for example:
          BEATPORT_ACCESS_TOKEN=$(tagslut auth token-get beatport)
        """
        _emit_provider_token(provider, tokens_path)

    @auth.command("login")
    @click.argument('provider')
    @click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
    def auth_login(provider, tokens_path):  # type: ignore  # TODO: mypy-strict
        """
        Authenticate with a provider interactively.

        Supported providers:
        - tidal: Device authorization (opens browser)
        - beatport: Manual token from browser DevTools
        """
        from tagslut.metadata.auth import DEFAULT_TOKENS_PATH, TokenManager

        path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
        token_manager = TokenManager(path)

        if provider == 'tidal':
            _tidal_device_login(token_manager)

        elif provider == 'beatport':
            _beatport_token_input(token_manager)

        else:
            click.echo(f"Interactive login not supported for {provider}.")
