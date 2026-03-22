"""Shared authentication helpers for provider login flows."""

from __future__ import annotations

import time

import click


def _tidal_device_login(token_manager) -> None:  # type: ignore  # TODO: mypy-strict
    """Handle Tidal device authorization flow."""
    click.echo("Starting Tidal device authorization...")

    device_auth = token_manager.start_tidal_device_auth()
    if not device_auth:
        click.echo("Failed to start device authorization.")
        return

    user_code = device_auth.get("userCode")
    verification_uri = device_auth.get("verificationUriComplete") or device_auth.get("verificationUri")
    device_code = device_auth.get("deviceCode")
    expires_in = device_auth.get("expiresIn", 300)
    interval = device_auth.get("interval", 5)

    click.echo(f"\n1. Go to: {verification_uri}")
    if user_code:
        click.echo(f"2. Enter code: {user_code}")
    click.echo(f"\nWaiting for authorization (expires in {expires_in}s)...")

    # Poll for completion
    start_time = time.time()
    while time.time() - start_time < expires_in:
        time.sleep(interval)

        token = token_manager.complete_tidal_device_auth(device_code)
        if token:
            click.echo("\nTidal authentication successful!")
            click.echo(f"Token expires at: {time.ctime(token.expires_at)}")
            return

        # Show progress
        elapsed = int(time.time() - start_time)
        click.echo(f"  Waiting... ({elapsed}s)", nl=False)
        click.echo("\r", nl=False)

    click.echo("\nAuthorization timed out. Please try again.")


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
