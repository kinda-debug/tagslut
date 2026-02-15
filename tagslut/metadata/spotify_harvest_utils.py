"""
Spotify token utilities for shell-based harvesters.

This module provides a single source of truth for Spotify authentication
in shell scripts and other harvesters that need to make direct HTTP calls
to the Spotify API.

Usage from Python:
    from tagslut.metadata.spotify_harvest_utils import (
        spotify_available,
        get_spotify_headers,
    )
    
    if spotify_available():
        headers = get_spotify_headers()
        # Use headers in requests

Usage from shell (CLI entry point):
    # Print Authorization header value (exits non-zero if unavailable)
    python3 -m tagslut.metadata.spotify_harvest_utils print-header
    
    # Check if Spotify is available (exit code 0 = yes, 1 = no)
    python3 -m tagslut.metadata.spotify_harvest_utils check
    
    # Print full header line for curl -H
    python3 -m tagslut.metadata.spotify_harvest_utils curl-header

The module caches the token result at module level so repeated calls
within the same process are cheap. Token refresh is attempted only once
per process via TokenManager.ensure_valid_token().
"""

import logging
import sys
from typing import Optional, Dict

from tagslut.metadata.auth import TokenManager, TokenInfo

logger = logging.getLogger("tagslut.metadata.spotify_harvest_utils")

# Module-level cache for token state
_token_manager: Optional[TokenManager] = None
_spotify_token: Optional[TokenInfo] = None
_spotify_checked: bool = False
_spotify_available: bool = False


def _ensure_initialized() -> None:
    """
    Initialize token manager and check Spotify availability once.
    
    This is called lazily on first access. The result is cached so
    subsequent calls are essentially free.
    """
    global _token_manager, _spotify_token, _spotify_checked, _spotify_available
    
    if _spotify_checked:
        return
    
    _spotify_checked = True
    
    try:
        _token_manager = TokenManager()
        
        # Check if Spotify is configured
        if not _token_manager.is_configured("spotify"):
            logger.info("Spotify not configured in tokens.json")
            _spotify_available = False
            return
        
        # Try to get a valid token (refreshes if needed)
        _spotify_token = _token_manager.ensure_valid_token("spotify")
        
        if _spotify_token and _spotify_token.access_token:
            _spotify_available = True
            logger.debug("Spotify token available")
        else:
            _spotify_available = False
            logger.warning("Spotify token refresh failed or returned empty token")
            
    except Exception as e:
        logger.error("Failed to initialize Spotify token: %s", e)
        _spotify_available = False


def spotify_available() -> bool:
    """
    Check if Spotify is available for this run.
    
    Returns True if:
    - Spotify credentials are configured in tokens.json
    - A valid access token was obtained (or refreshed)
    
    This function caches its result, so it's safe to call repeatedly.
    Token refresh is attempted only once per process.
    
    Returns:
        True if Spotify API calls can be made, False otherwise
    """
    _ensure_initialized()
    return _spotify_available


def get_spotify_headers() -> Optional[Dict[str, str]]:
    """
    Get HTTP headers dict for Spotify API requests.
    
    Returns a dict with Authorization header if Spotify is available,
    or None if Spotify is unavailable.
    
    Example:
        headers = get_spotify_headers()
        if headers:
            response = requests.get(url, headers=headers)
    
    Returns:
        Dict with "Authorization" key, or None if unavailable
    """
    _ensure_initialized()
    
    if not _spotify_available or not _spotify_token:
        return None
    
    return {
        "Authorization": f"Bearer {_spotify_token.access_token}",
        "Accept": "application/json",
    }


def get_spotify_token() -> Optional[str]:
    """
    Get the raw Spotify access token string.
    
    Returns:
        Access token string, or None if unavailable
    """
    _ensure_initialized()
    
    if not _spotify_available or not _spotify_token:
        return None
    
    return _spotify_token.access_token


def _cli_main() -> int:
    """
    CLI entry point for shell script integration.
    
    Commands:
        check       - Exit 0 if Spotify available, 1 if not (no output)
        print-token - Print just the access token
        print-header - Print "Bearer <token>" (the Authorization header value)
        curl-header - Print "Authorization: Bearer <token>" (for curl -H)
    
    Returns:
        Exit code (0 = success, 1 = Spotify unavailable, 2 = usage error)
    """
    if len(sys.argv) < 2:
        print("Usage: python3 -m tagslut.metadata.spotify_harvest_utils <command>", file=sys.stderr)
        print("Commands: check, print-token, print-header, curl-header", file=sys.stderr)
        return 2
    
    command = sys.argv[1].lower()
    
    if command == "check":
        # Silent check - just exit code
        return 0 if spotify_available() else 1
    
    elif command == "print-token":
        token = get_spotify_token()
        if token:
            print(token)
            return 0
        else:
            print("ERROR: Spotify token unavailable", file=sys.stderr)
            return 1
    
    elif command == "print-header":
        token = get_spotify_token()
        if token:
            print(f"Bearer {token}")
            return 0
        else:
            print("ERROR: Spotify token unavailable", file=sys.stderr)
            return 1
    
    elif command == "curl-header":
        token = get_spotify_token()
        if token:
            print(f"Authorization: Bearer {token}")
            return 0
        else:
            print("ERROR: Spotify token unavailable", file=sys.stderr)
            return 1
    
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print("Commands: check, print-token, print-header, curl-header", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(_cli_main())
