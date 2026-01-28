"""
Apple/iTunes Search API provider.

This is a public, unauthenticated API. It's useful for general-purpose
searches but lacks some of the detailed metadata of other services.

API Reference: https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html
"""

import logging
from typing import Optional, List, Dict, Any

from dedupe.metadata.models import ProviderTrack, MatchConfidence
from dedupe.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("dedupe.metadata.providers.itunes")


class iTunesProvider(AbstractProvider):
    """
    Apple/iTunes Search API provider.

    Supports:
    - Text search: GET /search?term={query}&entity=song
    - ISRC search: Client-side filtering on text search results.
    - No direct track-by-ID lookup.
    """

    name = "itunes"
    supports_isrc_search = False

    rate_limit_config = RateLimitConfig(
        min_delay=0.5,  # iTunes API: reduced for faster enrichment
        max_retries=5,
        base_backoff=10.0,
    )

    BASE_URL = "https://itunes.apple.com"
    COUNTRY = "US"

    def __init__(self, token_manager=None):
        # iTunes doesn't require a token manager
        super().__init__(token_manager=None)

    def _get_default_headers(self) -> Dict[str, str]:
        """No auth headers needed."""
        return {"Accept": "application/json"}

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        """
        Not supported by iTunes Search API.

        You can look up by ID, but it's a different API (Apple Music).
        For this provider, we stick to the public search API.
        """
        logger.debug("iTunes does not support fetch_by_id via the public search API.")
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
            "term": query,
            "entity": "song",
            "country": self.COUNTRY,
            "limit": min(limit, 200),
        }

        response = self._make_request("GET", url, params=params)
        if response is None or response.status_code != 200:
            logger.warning("iTunes search failed for query: %s", query)
            return []

        try:
            data = response.json()
            tracks = data.get("results", [])
            return [self._normalize_track(t) for t in tracks]
        except Exception as e:
            logger.error("Failed to parse iTunes search response: %s", e)
            return []

    def _normalize_track(self, data: Dict[str, Any]) -> ProviderTrack:
        """
        Normalize iTunes search result to ProviderTrack.

        iTunes result structure:
        {
            "trackId": ...,
            "trackName": "...",
            "artistName": "...",
            "collectionName": "...", // Album
            "trackTimeMillis": ...,
            "primaryGenreName": "...",
            "releaseDate": "...", // YYYY-MM-DDTHH:mm:ssZ
            "trackNumber": ...,
            "discNumber": ...,
            "artworkUrl100": "...", // Album art
            "trackViewUrl": "...",
        }
        """
        release_date = data.get("releaseDate", "")
        year = None
        if release_date:
            try:
                year = int(release_date[:4])
            except (ValueError, IndexError):
                pass

        return ProviderTrack(
            service="itunes",
            service_track_id=str(data.get("trackId")),
            title=data.get("trackName"),
            artist=data.get("artistName"),
            album=data.get("collectionName"),
            duration_ms=data.get("trackTimeMillis"),
            isrc=data.get("isrc"),
            genre=data.get("primaryGenreName"),
            year=year,
            album_art_url=data.get("artworkUrl100"),
            url=data.get("trackViewUrl"),
            track_number=data.get("trackNumber"),
            disc_number=data.get("discNumber"),
            explicit="explicit" in (data.get("trackExplicitness") or ""),
            match_confidence=MatchConfidence.NONE,
            raw=data,
        )
