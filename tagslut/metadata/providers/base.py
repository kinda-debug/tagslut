"""
Base provider class and rate limiting utilities.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import httpx

from tagslut.metadata.models.types import ProviderTrack, MatchConfidence
from tagslut.metadata.auth import TokenManager, TokenInfo

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration for a provider."""
    min_delay: float = 0.5      # Minimum seconds between requests
    max_retries: int = 3        # Maximum retry attempts
    base_backoff: float = 2.0   # Base backoff multiplier
    max_backoff: float = 60.0   # Maximum backoff delay


class RateLimiter:
    """
    Simple rate limiter with exponential backoff.

    Tracks the last request time and enforces minimum delay between requests.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._last_request_time: float = 0
        self._consecutive_errors: int = 0

    def wait(self) -> None:
        """Wait the appropriate time before next request."""
        now = time.time()
        elapsed = now - self._last_request_time

        # Calculate delay with backoff for errors
        delay = self.config.min_delay
        if self._consecutive_errors > 0:
            backoff = self.config.base_backoff ** self._consecutive_errors
            delay = min(delay * backoff, self.config.max_backoff)

        if elapsed < delay:
            sleep_time = delay - elapsed
            logger.debug("Rate limiting: sleeping %.2fs", sleep_time)
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    def record_success(self) -> None:
        """Record a successful request."""
        self._consecutive_errors = 0

    def record_error(self) -> None:
        """Record a failed request."""
        self._consecutive_errors += 1

    @property
    def should_retry(self) -> bool:
        """Check if we should retry after error."""
        return self._consecutive_errors < self.config.max_retries


class AbstractProvider(ABC):
    """
    Abstract base class for metadata providers.

    All providers must implement:
    - fetch_by_id: Get track by provider-specific ID
    - search: Search for tracks by text query
    - search_by_isrc: Search by ISRC (if supported)

    Providers inherit common functionality:
    - Rate limiting
    - Retry with exponential backoff
    - Token management
    """

    # Provider name (e.g., "spotify", "beatport")
    name: str = "unknown"

    # Rate limit config (can be overridden by subclasses)
    rate_limit_config = RateLimitConfig()

    # Whether this provider supports ISRC search natively
    supports_isrc_search: bool = False

    def __init__(self, token_manager: TokenManager):
        self.token_manager = token_manager
        self.rate_limiter = RateLimiter(self.rate_limit_config)
        self._client: Optional[httpx.Client] = None
        # Track if auth has permanently failed (e.g., 403 forbidden with bad credentials)
        self._auth_permanently_failed: bool = False
        self._auth_failure_reason: Optional[str] = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-initialized HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):  # type: ignore  # TODO: mypy-strict
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # type: ignore  # TODO: mypy-strict
        self.close()

    def _get_token(self) -> Optional[TokenInfo]:
        """Get valid token for this provider."""
        if self.token_manager is None:
            return None
        return self.token_manager.ensure_valid_token(self.name)

    def _make_request(  # type: ignore  # TODO: mypy-strict
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Optional[httpx.Response]:
        """
        Make an HTTP request with rate limiting and retry.

        Returns None if all retries fail or if auth has permanently failed.
        """
        # If auth has permanently failed for this provider, skip immediately
        if self._auth_permanently_failed:
            logger.debug(
                "%s: Skipping request (auth permanently failed: %s)",
                self.name,
                self._auth_failure_reason,
            )
            return None

        all_headers = self._get_default_headers()
        if headers:
            all_headers.update(headers)

        while True:
            self.rate_limiter.wait()

            try:
                response = self.client.request(
                    method,
                    url,
                    headers=all_headers,
                    params=params,
                    **kwargs,
                )

                # Handle rate limiting responses
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    logger.warning(
                        "%s: Rate limited, waiting %ds",
                        self.name,
                        retry_after,
                    )
                    time.sleep(retry_after)
                    self.rate_limiter.record_error()
                    if self.rate_limiter.should_retry:
                        continue
                    return None

                # Handle auth errors - distinguish 401 (expired) vs 403 (forbidden)
                if response.status_code == 401:
                    # 401 Unauthorized - token expired or invalid, try refresh
                    logger.warning(
                        "%s: Token expired or invalid (401), attempting refresh",
                        self.name,
                    )
                    if self._refresh_token_and_retry(response):
                        all_headers = self._get_default_headers()
                        if headers:
                            all_headers.update(headers)
                        continue
                    return None

                if response.status_code == 403:
                    # 403 handling differs by provider type:
                    # - Auth providers: treat as permanent credential failure.
                    # - Public/no-auth providers: fail this request only.
                    response_body = ""
                    try:
                        response_body = response.text[:500]  # Limit to 500 chars
                    except Exception as e:
                        logger.debug("%s: Failed to read 403 response body: %s", self.name, e)
                        pass

                    if self.token_manager is None:
                        logger.warning(
                            "%s: Access forbidden (403) on public endpoint. Response: %s. "
                            "Skipping this request only.",
                            self.name,
                            response_body or "(empty)",
                        )
                        self.rate_limiter.record_error()
                        return None

                    logger.error(
                        "%s: Access forbidden (403) - credentials may be invalid or lack required scope. "
                        "Response: %s. Skipping all further requests for this provider.",
                        self.name,
                        response_body or "(empty)",
                    )
                    self._auth_permanently_failed = True
                    self._auth_failure_reason = (
                        f"403 Forbidden: {response_body[:100] if response_body else 'no details'}"
                    )
                    return None

                # Handle server errors with retry
                if response.status_code >= 500:
                    self.rate_limiter.record_error()
                    if self.rate_limiter.should_retry:
                        logger.warning(
                            "%s: Server error (%d), retrying...",
                            self.name,
                            response.status_code,
                        )
                        continue
                    return None

                self.rate_limiter.record_success()
                return response

            except httpx.HTTPError as e:
                logger.warning("%s: Request failed: %s", self.name, e)
                self.rate_limiter.record_error()
                if self.rate_limiter.should_retry:
                    continue
                return None

    def _refresh_token_and_retry(self, failed_response: Optional[httpx.Response] = None) -> bool:
        """
        Attempt to refresh token. Returns True if successful.

        If refresh fails, marks auth as permanently failed to prevent retry loops.
        """
        token = self.token_manager.ensure_valid_token(self.name)

        if token is None or not token.access_token:
            # Token refresh failed - mark as permanent failure
            response_hint = ""
            if failed_response:
                try:
                    response_hint = f" API response: {failed_response.text[:200]}"
                except Exception as e:
                    logger.debug("%s: Failed to read failed response payload hint: %s", self.name, e)
                    pass

            logger.error(
                "%s: Token refresh failed - check credentials in tokens.json.%s "
                "Skipping all further requests for this provider.",
                self.name,
                response_hint,
            )
            self._auth_permanently_failed = True
            self._auth_failure_reason = "Token refresh failed"
            return False

        return True

    @abstractmethod
    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for requests (including auth)."""
        pass

    @abstractmethod
    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        """
        Fetch track metadata by provider-specific ID.

        Args:
            track_id: The provider's track ID

        Returns:
            ProviderTrack with match_confidence=EXACT, or None if not found
        """
        pass

    @abstractmethod
    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> List[ProviderTrack]:
        """
        Search for tracks by text query.

        Args:
            query: Search query (typically "artist title")
            limit: Maximum results to return

        Returns:
            List of ProviderTrack objects (match_confidence set by caller based on scoring)
        """
        pass

    def search_by_isrc(self, isrc: str) -> List[ProviderTrack]:
        """
        Search for tracks by ISRC.

        Default implementation uses generic search with ISRC as query.
        Subclasses with native ISRC support should override.

        Args:
            isrc: International Standard Recording Code

        Returns:
            List of ProviderTrack objects with matching ISRC
        """
        # Default: search with ISRC as query, filter results
        results = self.search(isrc, limit=10)
        return [t for t in results if t.isrc and t.isrc.upper() == isrc.upper()]

    def _normalize_track(self, raw: Dict[str, Any]) -> ProviderTrack:
        """
        Normalize raw API response to ProviderTrack.

        Subclasses should implement this to handle provider-specific formats.
        """
        raise NotImplementedError("Subclass must implement _normalize_track")


def score_text_similarity(a: Optional[str], b: Optional[str]) -> float:
    """
    Simple text similarity score (0.0 to 1.0).

    Uses lowercase comparison with common normalization.
    """
    if not a or not b:
        return 0.0

    # Normalize
    a_norm = a.lower().strip()
    b_norm = b.lower().strip()

    if a_norm == b_norm:
        return 1.0

    # Check if one contains the other
    if a_norm in b_norm or b_norm in a_norm:
        return 0.8

    # Simple word overlap
    a_words = set(a_norm.split())
    b_words = set(b_norm.split())
    if not a_words or not b_words:
        return 0.0

    overlap = len(a_words & b_words)
    union = len(a_words | b_words)
    return overlap / union if union > 0 else 0.0


def classify_match_confidence(
    local_title: Optional[str],
    local_artist: Optional[str],
    local_duration_s: Optional[float],
    track: ProviderTrack,
    strong_duration_tolerance: float = 10.0,
    medium_duration_tolerance: float = 20.0,
) -> MatchConfidence:
    """
    Classify match confidence based on title, artist, and duration similarity.

    Args:
        local_title: Title from local file
        local_artist: Artist from local file
        local_duration_s: Duration in seconds from local file
        track: Provider track to compare
        strong_duration_tolerance: Max duration diff for STRONG match
        medium_duration_tolerance: Max duration diff for MEDIUM match

    Returns:
        MatchConfidence level
    """
    title_sim = score_text_similarity(local_title, track.title)
    artist_sim = score_text_similarity(local_artist, track.artist)

    # Duration difference
    duration_diff = None
    if local_duration_s is not None and track.duration_s is not None:
        duration_diff = abs(local_duration_s - track.duration_s)

    # Strong match: good title + artist, duration within tolerance
    if title_sim >= 0.7 and artist_sim >= 0.7:
        if duration_diff is None or duration_diff <= strong_duration_tolerance:
            return MatchConfidence.STRONG
        elif duration_diff <= medium_duration_tolerance:
            return MatchConfidence.MEDIUM

    # Medium match: partial title/artist match with close duration
    if (title_sim >= 0.5 or artist_sim >= 0.5) and duration_diff is not None:
        if duration_diff <= medium_duration_tolerance:
            return MatchConfidence.MEDIUM

    # Weak match: only duration is close
    if duration_diff is not None and duration_diff <= strong_duration_tolerance:
        return MatchConfidence.WEAK

    return MatchConfidence.NONE
