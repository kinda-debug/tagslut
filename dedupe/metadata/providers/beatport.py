"""
Beatport API V4 provider.

Beatport is a primary source for electronic music metadata, especially BPM, key, and genre.
It uses OAuth2 with client credentials flow for authentication.

API Reference: https://api.beatport.com/v4/docs/
"""

import logging
from typing import Optional, List, Dict, Any

from dedupe.metadata.models import ProviderTrack, MatchConfidence
from dedupe.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("dedupe.metadata.providers.beatport")


class BeatportProvider(AbstractProvider):
    """
    Beatport API v4 provider.

    Supports:
    - Track by ID: GET /v4/catalog/tracks/{id}/
    - Text search: GET /v4/catalog/search/?q={query}&type=tracks
    - ISRC search: Client-side filtering on text search results.
    """

    name = "beatport"
    supports_isrc_search = False

    rate_limit_config = RateLimitConfig(
        min_delay=0.5,  # As requested
        max_retries=3,
        base_backoff=2.0,
    )

    BASE_URL = "https://api.beatport.com/v4/catalog"

    def _get_default_headers(self) -> Dict[str, str]:
        """Get headers with Bearer token."""
        token = self._get_token()
        headers = {
            "Accept": "application/json",
        }
        if token and token.access_token:
            headers["Authorization"] = f"Bearer {token.access_token}"
        return headers

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        """
        Fetch track by Beatport ID.

        Args:
            track_id: Beatport track ID (e.g., "12345")

        Returns:
            ProviderTrack with match_confidence=EXACT, or None
        """
        url = f"{self.BASE_URL}/tracks/{track_id}/"

        response = self._make_request("GET", url)
        if response is None or response.status_code != 200:
            logger.warning("Failed to fetch Beatport track %s", track_id)
            return None

        try:
            data = response.json()
            track = self._normalize_track(data)
            track.match_confidence = MatchConfidence.EXACT
            return track
        except Exception as e:
            logger.error("Failed to parse Beatport response: %s", e)
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
        url = f"{self.BASE_URL}/search/"
        params = {
            "q": query,
            "type": "track",
            "per_page": min(limit, 50),
        }

        response = self._make_request("GET", url, params=params)
        if response is None or response.status_code != 200:
            logger.warning("Beatport search failed for query: %s", query)
            return []

        try:
            data = response.json()
            tracks = data.get("tracks", [])
            return [self._normalize_track(t) for t in tracks]
        except Exception as e:
            logger.error("Failed to parse Beatport search response: %s", e)
            return []

    def _normalize_track(self, data: Dict[str, Any]) -> ProviderTrack:
        """
        Normalize Beatport track object to ProviderTrack.

        Beatport track structure (simplified):
        {
            "id": 12345,
            "name": "...",
            "artists": [{"name": "..."}],
            "release": {"name": "..."},
            "length_ms": 123456,
            "bpm": 128,
            "key": {"name": "A minor"},
            "genre": {"name": "Techno"},
            "label": {"name": "..."},
            "publish_date": "YYYY-MM-DD",
            "isrc": "..."
        }
        """
        artists = data.get("artists", [])
        artist_name = ", ".join(a.get("name", "") for a in artists) if artists else None

        release = data.get("release", {})
        album_name = release.get("name")

        publish_date = data.get("publish_date", "")
        year = None
        if publish_date:
            try:
                year = int(publish_date[:4])
            except (ValueError, IndexError):
                pass
        
        key = data.get("key")
        key_name = key.get("name") if key else None

        genre = data.get("genre")
        genre_name = genre.get("name") if genre else None

        label = data.get("label")
        label_name = label.get("name") if label else None

        return ProviderTrack(
            service="beatport",
            service_track_id=str(data.get("id")),
            title=data.get("name"),
            artist=artist_name,
            album=album_name,
            duration_ms=data.get("length_ms"),
            isrc=data.get("isrc"),
            bpm=data.get("bpm"),
            key=key_name,
            genre=genre_name,
            label=label_name,
            year=year,
            album_art_url=data.get("image", {}).get("uri"),
            url=data.get("url"),
            match_confidence=MatchConfidence.NONE,  # Set by caller
            raw=data,
        )
