"""
Token management for metadata providers.

Handles storage, retrieval, and refresh of API tokens.

Supported auth flows:
- Spotify: Client credentials (client_id + client_secret)
- Tidal: Device authorization flow (no user credentials needed)
- Qobuz: Email/password login
- Beatport: Client credentials (client_id + client_secret)
- iTunes: No auth required (public API)
"""

import json
import logging
import os
import time
import base64
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
import httpx

logger = logging.getLogger("tagslut.metadata.auth")

DEFAULT_TOKENS_PATH = Path.home() / ".config" / "tagslut" / "tokens.json"

# =============================================================================
# Public App Credentials Configuration
# =============================================================================
# These credentials are PUBLIC/WELL-KNOWN values extracted from official client
# applications. They are NOT secrets - they are embedded in publicly distributed
# apps and are safe to include in source code. Many open-source projects use
# these same credentials.
#
# Environment variables can override these defaults if needed (e.g., for testing
# with different client IDs or if the defaults become invalid).
# =============================================================================

def _get_tidal_credentials() -> Tuple[str, str]:
    """
    Get Tidal client credentials.
    
    These are PUBLIC credentials from the tiddl project, embedded in the official
    Tidal desktop app. They are NOT secrets and are safe to include in source.
    Override via TIDAL_CLIENT_ID and TIDAL_CLIENT_SECRET env vars if needed.
    """
    # Default: base64-encoded public credentials from tiddl/Tidal desktop app
    default_encoded = "ZlgySnhkbW50WldLMGl4VDsxTm45QWZEQWp4cmdKRkpiS05XTGVBeUtHVkdtSU51WFBQTEhWWEF2eEFnPQ=="
    default_id, default_secret = base64.b64decode(default_encoded).decode().split(";")
    
    client_id = os.getenv("TIDAL_CLIENT_ID", default_id)
    client_secret = os.getenv("TIDAL_CLIENT_SECRET", default_secret)
    return client_id, client_secret


def _get_beatport_client_id() -> str:
    """
    Get Beatport DJ app client ID.
    
    This is a PUBLIC client ID extracted from dj.beatport.com. It is NOT a secret
    and is safe to include in source code.
    Override via BEATPORT_DJ_CLIENT_ID env var if needed.
    """
    default_id = "pz8kb0BFOrRhct2Wlq5mVoPdZnOa0hcsARuVjJbm"
    return os.getenv("BEATPORT_DJ_CLIENT_ID", default_id)


# Initialize credentials (can be overridden by environment variables)
# These are PUBLIC app credentials, not secrets - see docstrings above
TIDAL_CLIENT_ID, TIDAL_CLIENT_SECRET = _get_tidal_credentials()
BEATPORT_DJ_CLIENT_ID = _get_beatport_client_id()


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
        # None or 0 means expiration is unknown/not tracked
        if not self.expires_at:
            return False
        return time.time() > (self.expires_at - 300)


class TokenManager:
    """
    Manages API tokens for all providers.

    Tokens are stored in a JSON file with the structure:
    {
        "tidal": {
            "refresh_token": "...",
            "user_id": "...",
            "country_code": "US",
            "access_token": "...",
            "expires_at": 1234567890
        },
        "beatport": { ... },
        ...
    }
    
    Switching Accounts (e.g., Tidal):
    ---------------------------------
    To use a different account for any provider, simply edit the corresponding
    section in tokens.json. No code changes are required.
    
    For Tidal specifically:
    1. Run 'tagslut auth login tidal' to authenticate a new account, OR
    2. Manually update the 'tidal' section in tokens.json with:
       - refresh_token: Required. Copy from another authenticated session.
       - user_id: Optional. The Tidal user ID.
       - country_code: Optional. Defaults to "US".
    3. Re-run your CLI command. The new credentials will be used automatically.
    
    The TokenManager reads tokens.json on initialization and uses whatever
    credentials are present. It does not hardcode any particular account.
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
        access_token = data.get("access_token", "")

        # Return None if no access token (empty string counts as missing)
        if not access_token:
            return None

        return TokenInfo(
            access_token=access_token,
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

    def refresh_tidal_token(self) -> Optional[TokenInfo]:
        """
        Refresh Tidal access token using stored refresh_token.

        Tidal uses device authorization flow for initial auth, then refresh tokens.
        """
        if "tidal" not in self._tokens:
            logger.error("Tidal not configured. Run 'tagslut auth login tidal' first.")
            return None

        refresh_token = self._tokens["tidal"].get("refresh_token")
        if not refresh_token:
            logger.error("No Tidal refresh_token. Run 'tagslut auth login tidal' to authenticate.")
            return None

        try:
            response = httpx.post(
                "https://auth.tidal.com/v1/oauth2/token",
                data={
                    "client_id": TIDAL_CLIENT_ID,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                    "scope": "r_usr+w_usr+w_sub",
                },
                auth=(TIDAL_CLIENT_ID, TIDAL_CLIENT_SECRET),
                timeout=30.0,
            )
            response.raise_for_status()

            data = response.json()
            expires_at = time.time() + data.get("expires_in", 86400)

            self.set_token(
                "tidal",
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", refresh_token),  # May return new refresh token
                expires_at=expires_at,
                token_type=data.get("token_type", "Bearer"),
            )

            logger.info("Refreshed Tidal token (expires in %ds)", data.get("expires_in", 86400))
            return self.get_token("tidal")

        except httpx.HTTPError as e:
            logger.error("Failed to refresh Tidal token: %s", e)
            return None

    def start_tidal_device_auth(self) -> Optional[Dict[str, Any]]:
        """
        Start Tidal device authorization flow.

        Returns dict with:
        - device_code: Code to poll with
        - user_code: Code for user to enter
        - verification_uri: URL for user to visit
        - expires_in: Seconds until codes expire
        - interval: Polling interval in seconds
        """
        try:
            response = httpx.post(
                "https://auth.tidal.com/v1/oauth2/device_authorization",
                data={
                    "client_id": TIDAL_CLIENT_ID,
                    "scope": "r_usr+w_usr+w_sub",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error("Failed to start Tidal device auth: %s", e)
            return None

    def complete_tidal_device_auth(self, device_code: str) -> Optional[TokenInfo]:
        """
        Complete Tidal device authorization by polling for token.

        Call this after user has authorized at the verification_uri.
        Returns None if authorization is still pending.
        Raises exception if authorization failed/expired.
        """
        try:
            response = httpx.post(
                "https://auth.tidal.com/v1/oauth2/token",
                data={
                    "client_id": TIDAL_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "scope": "r_usr+w_usr+w_sub",
                },
                auth=(TIDAL_CLIENT_ID, TIDAL_CLIENT_SECRET),
                timeout=30.0,
            )

            data = response.json()

            if response.status_code != 200:
                error = data.get("error", "unknown")
                if error == "authorization_pending":
                    return None  # Still waiting for user
                elif error == "slow_down":
                    return None  # Need to slow down polling
                else:
                    raise Exception(f"Tidal auth failed: {error} - {data.get('error_description', '')}")

            expires_at = time.time() + data.get("expires_in", 86400)

            self.set_token(
                "tidal",
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                expires_at=expires_at,
                token_type=data.get("token_type", "Bearer"),
            )

            logger.info("Tidal authentication successful")
            return self.get_token("tidal")

        except httpx.HTTPError as e:
            logger.error("Failed to complete Tidal auth: %s", e)
            return None

    def refresh_beatport_token(self) -> Optional[TokenInfo]:
        """
        Refresh Beatport access token.

        Beatport doesn't have a public OAuth flow like Spotify/Tidal.
        Tokens must be obtained manually from dj.beatport.com browser DevTools.

        To get a token:
        1. Go to https://dj.beatport.com
        2. Open DevTools (F12) → Network tab
        3. Look for requests to api.beatport.com
        4. Copy the Bearer token from the Authorization header
        5. Paste it into tokens.json under beatport.access_token
        """
        # Try custom client credentials if configured (partner access)
        creds = self.get_credentials("beatport")
        if creds.get("client_id") and creds.get("client_secret"):
            try:
                response = httpx.post(
                    "https://api.beatport.com/v4/auth/o/token/",
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "grant_type": "client_credentials",
                        "client_id": creds["client_id"],
                        "client_secret": creds["client_secret"],
                    },
                    timeout=30.0,
                )
                response.raise_for_status()

                data = response.json()
                expires_at = time.time() + data.get("expires_in", 3600)

                self.set_token(
                    "beatport",
                    access_token=data["access_token"],
                    expires_at=expires_at,
                    token_type=data.get("token_type", "Bearer"),
                )

                logger.info("Refreshed Beatport token (expires in %ds)", data.get("expires_in", 3600))
                return self.get_token("beatport")

            except httpx.HTTPError as e:
                logger.debug("Partner credentials failed: %s", e)

        # Check for manually-set access token
        if "beatport" in self._tokens:
            access_token = self._tokens["beatport"].get("access_token")
            expires_at = self._tokens["beatport"].get("expires_at")
            if access_token:
                token = TokenInfo(access_token=access_token, expires_at=expires_at)
                if token.is_expired:
                    logger.warning("Beatport token expired. Get a fresh one from dj.beatport.com DevTools.")
                else:
                    logger.debug("Using existing Beatport access token")
                return token

        # Beatport has unauthenticated fallbacks; missing token is not fatal.
        logger.debug("No Beatport token configured; falling back to public endpoints.")
        return None

    def login_qobuz(self, email: str, password: str, app_id: Optional[str] = None) -> Optional[TokenInfo]:
        """
        Login to Qobuz with email/password to get user_auth_token.

        Qobuz doesn't use OAuth2 - it uses a simple login endpoint.

        Args:
            email: Qobuz account email
            password: Qobuz account password
            app_id: Optional app_id (uses default if not provided)
        """
        if "qobuz" not in self._tokens:
            self._tokens["qobuz"] = {}

        # Use provided app_id, or stored one, or default
        # Default app_id from qobuz-dl (well-known, works for API access)
        default_app_id = "950096963"
        app_id = app_id or self._tokens["qobuz"].get("app_id") or default_app_id

        try:
            # Qobuz uses MD5 hash of password
            password_hash = hashlib.md5(password.encode()).hexdigest()

            response = httpx.post(
                "https://www.qobuz.com/api.json/0.2/user/login",
                params={"app_id": app_id},
                data={
                    "email": email,
                    "password": password_hash,
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                },
                timeout=30.0,
            )

            if response.status_code == 401:
                logger.error("Qobuz login failed: invalid credentials")
                return None

            response.raise_for_status()

            data = response.json()
            user_auth_token = data.get("user_auth_token")

            if not user_auth_token:
                logger.error("Qobuz login response missing user_auth_token")
                return None

            # Store app_id and token
            self._tokens["qobuz"]["app_id"] = app_id
            self._tokens["qobuz"]["user_auth_token"] = user_auth_token
            self._tokens["qobuz"]["access_token"] = user_auth_token
            self._save_tokens()

            logger.info("Logged into Qobuz successfully")
            return TokenInfo(access_token=user_auth_token)

        except httpx.HTTPError as e:
            logger.error("Failed to login to Qobuz: %s", e)
            return None

    def ensure_valid_token(self, provider: str) -> Optional[TokenInfo]:
        """
        Ensure we have a valid token for a provider.

        Refreshes if expired or missing. Supports auto-refresh for:
        - tidal (refresh token) - needs initial device auth, then auto-refreshes
        - beatport (client credentials) - needs client_id + client_secret

        Manual login required for:
        - qobuz (email/password) - run 'tagslut auth login qobuz'
        - tidal (first time) - run 'tagslut auth login tidal'

        No auth needed for:
        - itunes (public API)
        """
        token = self.get_token(provider)

        if token is None or token.is_expired:
            if provider == "tidal":
                # Tidal needs refresh_token from device auth
                if self._tokens.get("tidal", {}).get("refresh_token"):
                    return self.refresh_tidal_token()
                else:
                    logger.warning("Tidal not authenticated. Run 'tagslut auth login tidal'")
                    return None
            elif provider == "beatport":
                return self.refresh_beatport_token()
            elif provider == "qobuz":
                # Qobuz tokens are long-lived, just check if we have one
                if self._tokens.get("qobuz", {}).get("user_auth_token"):
                    return TokenInfo(access_token=self._tokens["qobuz"]["user_auth_token"])
                logger.warning("Qobuz not authenticated. Run 'tagslut auth login qobuz'")
                return None
            elif provider == "itunes":
                # iTunes doesn't need auth
                return TokenInfo(access_token="")
            elif provider == "apple_music":
                # Apple Music extracts token dynamically in the provider
                return TokenInfo(access_token="")
            else:
                logger.debug("No refresh logic for provider: %s", provider)
                return token

        return token

    def status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all configured providers."""
        all_providers = ["beatport", "tidal", "qobuz", "itunes", "apple_music"]
        result = {}

        for provider in all_providers:
            configured = self.is_configured(provider)
            token = self.get_token(provider)

            # Special cases for providers that don't need auth
            if provider == "itunes":
                result[provider] = {
                    "configured": True,
                    "has_token": True,
                    "expired": False,
                    "expires_at": None,
                    "auth_type": "none (public API)",
                }
                continue

            if provider == "apple_music":
                result[provider] = {
                    "configured": True,
                    "has_token": True,
                    "expired": False,
                    "expires_at": None,
                    "auth_type": "dynamic bearer (extracted from web)",
                }
                continue

            if provider == "beatport":
                # Beatport can work via web scraping OR authenticated API
                bp_token = self.get_token("beatport")
                has_auth = bp_token is not None and bool(bp_token.access_token)
                result[provider] = {
                    "configured": True,
                    "has_token": has_auth,
                    "expired": bp_token.is_expired if bp_token else False,
                    "expires_at": bp_token.expires_at if bp_token else None,
                    "auth_type": "bearer token (API)" if has_auth else "web scraping",
                }
                continue

            result[provider] = {
                "configured": configured,
                "has_token": token is not None and bool(token.access_token),
                "expired": token.is_expired if token else None,
                "expires_at": token.expires_at if token else None,
            }

            # Add auth type info
            if provider == "beatport":
                result[provider]["auth_type"] = "client_credentials"
            elif provider == "tidal":
                result[provider]["auth_type"] = "device_auth"
            elif provider == "qobuz":
                result[provider]["auth_type"] = "email/password"

        return result

    def init_template(self) -> None:
        """
        Initialize tokens file with template structure.
        
        The tokens.json file stores credentials for all providers. Each provider
        section can be edited directly to switch accounts without code changes.
        
        For Tidal specifically:
        - To switch Tidal accounts, update the 'tidal' section with new credentials
        - Required fields: refresh_token (from device auth flow)
        - Optional fields: user_id, country_code, access_token, expires_at
        - Run 'tagslut auth login tidal' to authenticate a new account
        - Or manually copy refresh_token from another authenticated session
        """
        template = {
            "beatport": {
                "_comment": "Get credentials from https://api.beatport.com (if you have access)",
                "client_id": "",
                "client_secret": "",
            },
            "qobuz": {
                "_comment": "Run 'tagslut auth login qobuz' with your email/password",
            },
            "tidal": {
                "_comment": "Run 'tagslut auth login tidal' to authenticate via browser. "
                           "To switch accounts: update refresh_token (and optionally user_id, country_code) "
                           "in this section, then re-run the CLI. No code changes needed.",
                "refresh_token": "",
                "user_id": "",
                "country_code": "US",
            },
            "itunes": {
                "_comment": "No authentication required - iTunes Search API is public",
            },
            "apple_music": {
                "_comment": "No configuration required - bearer token is extracted dynamically from Apple Music web app",
            },
        }

        if self.tokens_path.exists():
            logger.warning("Tokens file already exists at %s", self.tokens_path)
            return

        self._tokens = template
        self._save_tokens()
        logger.info("Created tokens template at %s", self.tokens_path)

    def is_configured(self, provider: str) -> bool:
        """Check if a provider is properly configured for use."""
        if provider == "itunes":
            return True  # Always configured (public API)

        if provider == "apple_music":
            return True  # Always configured (token extracted dynamically from web)

        if provider == "beatport":
            # Beatport now works via web scraping without authentication
            return True

        if provider not in self._tokens:
            return False

        data = self._tokens[provider]

        if provider == "tidal":
            return bool(data.get("refresh_token"))
        elif provider == "qobuz":
            return bool(data.get("user_auth_token"))
        else:
            return False
