"""
Helper module to load Spotify partner tokens and build request headers.

Spotify Partner API tokens are short-lived and must be obtained manually from
the Spotify web player (open.spotify.com) browser DevTools. These tokens cannot
be refreshed programmatically - when they expire, you must manually extract
fresh tokens from the browser.

Token file location: spotify_partner_tokens.json at project root

Required keys in the JSON file:
    - spotify_partner_bearer: The Bearer token from Authorization header
    - spotify_partner_client_token: The client-token header value
    - spotify_partner_cookie (optional): Cookie header for additional auth

To obtain tokens:
    1. Open https://open.spotify.com in browser
    2. Open DevTools (F12) -> Network tab
    3. Play a track or browse to trigger API calls
    4. Find requests to api-partner.spotify.com
    5. Copy Authorization header (remove "Bearer " prefix) -> spotify_partner_bearer
    6. Copy client-token header -> spotify_partner_client_token
    7. Optionally copy Cookie header -> spotify_partner_cookie

Note: This module does NOT implement automatic token refresh. If tokens are
missing or invalid, explicit error messages are printed to help diagnose.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Optional

# Token file is at project root (two levels up from this module)
TOKEN_FILE = Path(__file__).parent.parent.parent / "spotify_partner_tokens.json"


def load_partner_tokens() -> Optional[Dict[str, str]]:
    """
    Load partner tokens from the JSON file.
    
    Returns:
        Dict with token keys, or None if file is missing/invalid.
        
    Prints diagnostic messages to stderr on failure to aid debugging.
    """
    if not TOKEN_FILE.exists():
        print(
            f"[spotify_partner_tokens] Token file not found: {TOKEN_FILE}\n"
            f"  Create this file with spotify_partner_bearer and spotify_partner_client_token keys.\n"
            f"  See module docstring for instructions on obtaining tokens.",
            file=sys.stderr
        )
        return None
    
    try:
        content = TOKEN_FILE.read_text()
        tokens = json.loads(content)
        print(f"[spotify_partner_tokens] Loaded tokens from {TOKEN_FILE}", file=sys.stderr)
        return tokens
    except json.JSONDecodeError as e:
        print(
            f"[spotify_partner_tokens] Invalid JSON in token file: {TOKEN_FILE}\n"
            f"  Parse error: {e}",
            file=sys.stderr
        )
        return None
    except IOError as e:
        print(
            f"[spotify_partner_tokens] Failed to read token file: {TOKEN_FILE}\n"
            f"  IO error: {e}",
            file=sys.stderr
        )
        return None


def get_partner_headers() -> Optional[Dict[str, str]]:
    """
    Build HTTP headers for Spotify partner API requests.
    
    Returns:
        Dict of headers ready for requests, or None if tokens unavailable.
        
    Prints diagnostic messages to stderr when required tokens are missing.
    """
    tokens = load_partner_tokens()
    if not tokens:
        # load_partner_tokens already printed diagnostics
        return None

    bearer = tokens.get("spotify_partner_bearer")
    client_token = tokens.get("spotify_partner_client_token")

    missing = []
    if not bearer:
        missing.append("spotify_partner_bearer")
    if not client_token:
        missing.append("spotify_partner_client_token")
    
    if missing:
        print(
            f"[spotify_partner_tokens] Missing required token(s): {', '.join(missing)}\n"
            f"  Token file: {TOKEN_FILE}\n"
            f"  These must be extracted from browser DevTools. See module docstring.",
            file=sys.stderr
        )
        return None

    headers = {
        "Authorization": f"Bearer {bearer}",
        "client-token": client_token,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://open.spotify.com",
        "Referer": "https://open.spotify.com/",
    }

    cookie = tokens.get("spotify_partner_cookie")
    if cookie:
        headers["Cookie"] = cookie

    return headers
