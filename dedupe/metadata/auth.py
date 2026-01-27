"""
Token management for metadata providers.

Handles storage, retrieval, and refresh of API tokens.
"""

import json
import logging
import time
import base64
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
import httpx

logger = logging.getLogger("dedupe.metadata.auth")

DEFAULT_TOKENS_PATH = Path.home() / ".config" / "dedupe" / "tokens.json"


@dataclass
class TokenInfo:
    """Token information for a provider."""
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[float] = None  # Unix timestamp
    token_type: str = "Bearer"

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 5 minute buffer)."""
        if self.expires_at is None:
            return False
        return time.time() > (self.expires_at - 300)


class TokenManager:
    """
    Manages API tokens for all providers.

    Tokens are stored in a JSON file with the structure:
    {
        "spotify": {
            "client_id": "...",
            "client_secret": "...",
            "access_token": "...",
            "refresh_token": "...",
            "expires_at": 1234567890
        },
        "beatport": { ... },
        ...
    }
    """

    def __init__(self, tokens_path: Optional[Path] = None):
        self.tokens_path = tokens_path or DEFAULT_TOKENS_PATH
        self._tokens: Dict[str, Dict[str, Any]] = {}
        self._load_tokens()

    def _load_tokens(self) -> None:
        """Load tokens from file."""
        if self.tokens_path.exists():
            try:
                with open(self.tokens_path, "r") as f:
                    self._tokens = json.load(f)
                logger.debug("Loaded tokens from %s", self.tokens_path)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load tokens: %s", e)
                self._tokens = {}
        else:
            logger.debug("No tokens file found at %s", self.tokens_path)
            self._tokens = {}

    def _save_tokens(self) -> None:
        """Save tokens to file."""
        self.tokens_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tokens_path, "w") as f:
            json.dump(self._tokens, f, indent=2)
        logger.debug("Saved tokens to %s", self.tokens_path)

    def get_token(self, provider: str) -> Optional[TokenInfo]:
        """Get token info for a provider."""
        if provider not in self._tokens:
            return None

        data = self._tokens[provider]
        if "access_token" not in data:
            return None

        return TokenInfo(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            expires_at=data.get("expires_at"),
            token_type=data.get("token_type", "Bearer"),
        )

    def set_token(
        self,
        provider: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[float] = None,
        **extra: Any,
    ) -> None:
        """Set token for a provider."""
        if provider not in self._tokens:
            self._tokens[provider] = {}

        self._tokens[provider].update({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            **extra,
        })
        self._save_tokens()

    def get_credentials(self, provider: str) -> Dict[str, str]:
        """Get client credentials for a provider."""
        if provider not in self._tokens:
            return {}

        data = self._tokens[provider]
        return {
            "client_id": data.get("client_id", ""),
            "client_secret": data.get("client_secret", ""),
        }

    def refresh_spotify_token(self) -> Optional[TokenInfo]:
        """
        Refresh Spotify access token using client credentials flow.

        This is the simplest OAuth flow - just uses client_id and client_secret
        to get an access token. Good for public data access.
        """
        creds = self.get_credentials("spotify")
        if not creds.get("client_id") or not creds.get("client_secret"):
            logger.error("Spotify client_id or client_secret not configured")
            return None

        # Base64 encode credentials
        auth_str = f"{creds['client_id']}:{creds['client_secret']}"
        auth_b64 = base64.b64encode(auth_str.encode()).decode()

        try:
            response = httpx.post(
                "https://accounts.spotify.com/api/token",
                headers={
                    "Authorization": f"Basic {auth_b64}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
                timeout=30.0,
            )
            response.raise_for_status()

            data = response.json()
            expires_at = time.time() + data.get("expires_in", 3600)

            self.set_token(
                "spotify",
                access_token=data["access_token"],
                expires_at=expires_at,
                token_type=data.get("token_type", "Bearer"),
            )

            logger.info("Refreshed Spotify token (expires in %ds)", data.get("expires_in", 3600))
            return self.get_token("spotify")

        except httpx.HTTPError as e:
            logger.error("Failed to refresh Spotify token: %s", e)
            return None

    def ensure_valid_token(self, provider: str) -> Optional[TokenInfo]:
        """
        Ensure we have a valid token for a provider.

        Refreshes if expired or missing.
        """
        token = self.get_token(provider)

        if token is None or token.is_expired:
            if provider == "spotify":
                return self.refresh_spotify_token()
            else:
                logger.warning("No refresh logic for provider: %s", provider)
                return token

        return token

    def status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all configured providers."""
        result = {}
        for provider, data in self._tokens.items():
            token = self.get_token(provider)
            result[provider] = {
                "configured": bool(data.get("client_id") or data.get("access_token")),
                "has_token": token is not None and bool(token.access_token),
                "expired": token.is_expired if token else None,
                "expires_at": token.expires_at if token else None,
            }
        return result

    def init_template(self) -> None:
        """Initialize tokens file with template structure."""
        template = {
            "spotify": {
                "client_id": "",
                "client_secret": "",
                "access_token": "",
                "refresh_token": "",
                "expires_at": None,
            },
            "beatport": {
                "access_token": "",
                "expires_at": None,
            },
            "qobuz": {
                "app_id": "",
                "user_auth_token": "",
            },
            "tidal": {
                "access_token": "",
                "refresh_token": "",
                "expires_at": None,
            },
            "apple": {
                "dev_token": "",
                "user_token": "",
            },
        }

        if self.tokens_path.exists():
            logger.warning("Tokens file already exists at %s", self.tokens_path)
            return

        self._tokens = template
        self._save_tokens()
        logger.info("Created tokens template at %s", self.tokens_path)
