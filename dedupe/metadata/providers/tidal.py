"""
Tidal OpenAPI v2 provider.

Tidal uses a JSON:API format, so responses are structured with `data` and `attributes`.
Authentication is via Bearer token.

API Reference: https://developer.tidal.com/apireference/
"""

import logging
from typing import Optional, List, Dict, Any

from dedupe.metadata.models import ProviderTrack, MatchConfidence
from dedupe.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("dedupe.metadata.providers.tidal")


class TidalProvider(AbstractProvider):
    """
    Tidal OpenAPI v2 provider.

    Supports:
    - Track by ID: GET /v2/tracks/{id}
    - Text search: GET /v2/search?types=tracks&query={query}
    - ISRC search: Client-side filtering on text search results.
    """

    name = "tidal"
    supports_isrc_search = False

    rate_limit_config = RateLimitConfig(
        min_delay=0.4,  # As requested
        max_retries=3,
        base_backoff=2.0,
    )

    BASE_URL = "https://openapi.tidal.com/v2"
    COUNTRY_CODE = "US"  # Should be configurable

    def _get_default_headers(self) -> Dict[str, str]:
        """Get headers with Bearer token."""
        token = self._get_token()
        headers = {
            "Accept": "application/vnd.tidal.v2+json",
            "Content-Type": "application/vnd.tidal.v2+json",
        }
        if token and token.access_token:
            headers["Authorization"] = f"Bearer {token.access_token}"
        return headers
    
    def _make_request(self, *args, **kwargs):
        """Add countryCode to all requests."""
        params = kwargs.get("params", {})
        if "countryCode" not in params:
            params["countryCode"] = self.COUNTRY_CODE
        kwargs["params"] = params
        
        return super()._make_request(*args, **kwargs)

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        """
        Fetch track by Tidal ID.

        Args:
            track_id: Tidal track ID.

        Returns:
            ProviderTrack with match_confidence=EXACT, or None
        """
        url = f"{self.BASE_URL}/tracks/{track_id}"
        params = {"include": "lyrics"}

        response = self._make_request("GET", url, params=params)
        if response is None or response.status_code != 200:
            logger.warning("Failed to fetch Tidal track %s", track_id)
            return None

        try:
            data = response.json()
            track_data = data.get("data", {}).get("attributes", {})
            track = self._normalize_track(track_data)
            track.match_confidence = MatchConfidence.EXACT
            return track
        except Exception as e:
            logger.error("Failed to parse Tidal response: %s", e)
            return None

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        """
        Search for tracks by text query.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of ProviderTrack objects
        """
        url = f"{self.BASE_URL}/search"
        params = {
            "query": query,
            "types": "tracks",
            "limit": min(limit, 50),
        }

        response = self._make_request("GET", url, params=params)
        if response is None or response.status_code != 200:
            logger.warning("Tidal search failed for query: %s", query)
            return []

        try:
            data = response.json()
            tracks = data.get("data", [])
            # In search, results are items with resource.attributes
            return [self._normalize_track(t.get("resource", {}).get("attributes", {})) for t in tracks]
        except Exception as e:
            logger.error("Failed to parse Tidal search response: %s", e)
            return []

    def _normalize_track(self, attributes: Dict[str, Any]) -> ProviderTrack:
        """
        Normalize Tidal track object (from attributes) to ProviderTrack.

        Tidal track attributes structure:
        {
            "title": "...",
            "artists": [{"name": "..."}],
            "album": {"title": "..."},
            "duration": 123,
            "isrc": "...",
            "releaseDate": "YYYY-MM-DD",
            ...
        }
        """
        if not attributes:
            return ProviderTrack(service="tidal")

        artists = attributes.get("artists", [])
        artist_name = ", ".join(a.get("name", "") for a in artists) if artists else None

        album = attributes.get("album", {})
        album_name = album.get("title")

        release_date = attributes.get("releaseDate")
        year = None
        if release_date:
            try:
                year = int(release_date[:4])
            except (ValueError, IndexError):
                pass
        
        duration_s = attributes.get("duration")
        duration_ms = duration_s * 1000 if duration_s else None

        return ProviderTrack(
            service="tidal",
            service_track_id=str(attributes.get("id")),
            title=attributes.get("title"),
            artist=artist_name,
            album=album_name,
            duration_ms=duration_ms,
            isrc=attributes.get("isrc"),
            year=year,
            album_art_url=album.get("image", {}).get("url"),
            url=album.get("tidalUrl"),
            track_number=attributes.get("trackNumber"),
            disc_number=attributes.get("volumeNumber"),
            explicit="EXPLICIT" in (attributes.get("parentalWarningType") or ""),
            match_confidence=MatchConfidence.NONE,
            raw=attributes,
        )
