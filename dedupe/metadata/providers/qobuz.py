"""
Qobuz API v0.2 provider.

Qobuz provides high-quality audio streams and downloads.
The API uses an app_id for basic access and an optional user_auth_token for user-specific data.

API Reference (unofficial): https://github.com/Qobuz/api-documentation/blob/master/endpoints/track.md
"""

import logging
from typing import Optional, List, Dict, Any

from dedupe.metadata.models import ProviderTrack, MatchConfidence
from dedupe.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("dedupe.metadata.providers.qobuz")


class QobuzProvider(AbstractProvider):
    """
    Qobuz API v0.2 provider.

    Supports:
    - Track by ID: GET /api.json/0.2/track/get?track_id={id}
    - Text search: GET /api.json/0.2/track/search?query={query}
    - ISRC search: Client-side filtering on text search results.
    """

    name = "qobuz"
    supports_isrc_search = False

    rate_limit_config = RateLimitConfig(
        min_delay=0.3,  # As requested
        max_retries=3,
        base_backoff=2.0,
    )

    BASE_URL = "https://www.qobuz.com/api.json/0.2"

    def _get_app_id(self) -> Optional[str]:
        """Get app_id from token manager."""
        creds = self.token_manager.get_credentials(self.name)
        return creds.get("app_id") if creds else None

    def _get_default_headers(self) -> Dict[str, str]:
        """Get headers with user_auth_token."""
        creds = self.token_manager.get_credentials(self.name)
        headers = {
            "Accept": "application/json",
        }
        if creds and creds.get("user_auth_token"):
            headers["user_auth_token"] = creds["user_auth_token"]
        return headers

    def _make_request(self, *args, **kwargs):
        """Add app_id to all requests."""
        app_id = self._get_app_id()
        if not app_id:
            logger.error("Qobuz app_id not configured.")
            return None
        
        params = kwargs.get("params", {})
        params["app_id"] = app_id
        kwargs["params"] = params
        
        return super()._make_request(*args, **kwargs)

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        """
        Fetch track by Qobuz ID.

        Args:
            track_id: Qobuz track ID.

        Returns:
            ProviderTrack with match_confidence=EXACT, or None
        """
        url = f"{self.BASE_URL}/track/get"
        params = {"track_id": track_id}

        response = self._make_request("GET", url, params=params)
        if response is None or response.status_code != 200:
            logger.warning("Failed to fetch Qobuz track %s", track_id)
            return None

        try:
            data = response.json()
            track = self._normalize_track(data)
            track.match_confidence = MatchConfidence.EXACT
            return track
        except Exception as e:
            logger.error("Failed to parse Qobuz response: %s", e)
            return None

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        """
        Search for tracks by text query.

        Args:
            query: Search query (e.g., "artist title")
            limit: Maximum results

        Returns:
            List of ProviderTrack objects
        """
        url = f"{self.BASE_URL}/track/search"
        params = {
            "query": query,
            "limit": min(limit, 50),
        }

        response = self._make_request("GET", url, params=params)
        if response is None or response.status_code != 200:
            logger.warning("Qobuz search failed for query: %s", query)
            return []

        try:
            data = response.json()
            tracks = data.get("tracks", {}).get("items", [])
            return [self._normalize_track(t) for t in tracks]
        except Exception as e:
            logger.error("Failed to parse Qobuz search response: %s", e)
            return []

    def _normalize_track(self, data: Dict[str, Any]) -> ProviderTrack:
        """
        Normalize Qobuz track object to ProviderTrack.

        Qobuz track structure (simplified):
        {
            "id": 12345,
            "title": "...",
            "performer": {"name": "..."},
            "album": {"title": "..."},
            "duration": 123,
            "isrc": "...",
            "release_date_original": "YYYY-MM-DD",
        }
        """
        performer = data.get("performer", {})
        artist_name = performer.get("name")

        album = data.get("album", {})
        album_name = album.get("title")

        release_date = data.get("release_date_original") or album.get("release_date_original")
        year = None
        if release_date:
            try:
                year = int(str(release_date)[:4])
            except (ValueError, IndexError):
                pass
        
        duration_s = data.get("duration")
        duration_ms = duration_s * 1000 if duration_s else None

        return ProviderTrack(
            service="qobuz",
            service_track_id=str(data.get("id")),
            title=data.get("title"),
            artist=artist_name,
            album=album_name,
            duration_ms=duration_ms,
            isrc=data.get("isrc"),
            year=year,
            album_art_url=album.get("image", {}).get("large"),
            url=f"https://www.qobuz.com/us-en/album/a/{album.get('id')}",
            track_number=data.get("track_number"),
            disc_number=data.get("media_number"),
            explicit=data.get("parental_warning"),
            match_confidence=MatchConfidence.NONE,  # Set by caller
            raw=data,
        )
