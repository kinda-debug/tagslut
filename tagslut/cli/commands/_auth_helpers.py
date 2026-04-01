"""Shared authentication helpers for provider login flows."""

from __future__ import annotations

import time

import click


def _tidal_device_login(token_manager) -> None:  # type: ignore  # TODO: mypy-strict
    """Delegate Tidal authentication to tiddl and sync token."""
    import subprocess

    click.echo("Delegating to tiddl for TIDAL authentication...")
    result = subprocess.run(["tiddl", "auth", "login"], check=False)
    if result.returncode != 0:
        click.echo("tiddl auth login failed. Is tiddl installed and configured?", err=True)
        return

    token = token_manager.sync_from_tiddl()
    if token:
        click.echo("TIDAL token synced from tiddl successfully.")
        if token.expires_at:
            click.echo(f"Token expires at: {time.ctime(token.expires_at)}")
    else:
        click.echo(
            "Warning: tiddl login succeeded but token sync failed. Check ~/.tiddl/auth.json",
            err=True,
        )


def _beatport_token_input(token_manager) -> None:  # type: ignore  # TODO: mypy-strict
    """Handle manual Beatport token input."""
    click.echo("Beatport Token Setup")
    click.echo("-" * 40)
    click.echo("Beatport requires manual token extraction from the browser.")
    click.echo("")
    click.echo("Steps:")
    click.echo("  1. Go to https://dj.beatport.com in your browser")
    click.echo("  2. Open DevTools (F12) -> Network tab")
    click.echo("  3. Look for any request to api.beatport.com")
    click.echo("  4. Find the 'Authorization: Bearer ...' header")
    click.echo("  5. Copy the token (everything after 'Bearer ')")
    click.echo("")
    click.echo("Note: These tokens expire every ~10 minutes.")
    click.echo("")

    token = click.prompt("Paste Bearer token (or 'skip' to cancel)")

    if token.lower() == 'skip':
        click.echo("Skipped.")
        return

    # Clean up token if user included "Bearer " prefix
    if token.lower().startswith("bearer "):
        token = token[7:]

    # Try to decode JWT to get expiration
    expires_at = None
    try:
        import base64
        import json

        # JWT is header.payload.signature
        parts = token.split('.')
        if len(parts) == 3:
            # Decode payload (add padding if needed)
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += '=' * padding
            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)
            expires_at = data.get('exp')
    except Exception:
        pass

    token_manager.set_token(
        "beatport",
        access_token=token,
        expires_at=expires_at,
    )

    if expires_at:
        click.echo(f"Beatport token saved! Expires at: {time.ctime(expires_at)}")
    else:
        click.echo("Beatport token saved! (couldn't determine expiration)")
