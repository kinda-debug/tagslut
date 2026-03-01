"""
Tidal API provider.

Uses Tidal's v1 API endpoints for search and track lookup.
Authentication is via Bearer token.
"""

import logging
import os
from typing import Optional, List, Dict, Any

from tagslut.metadata.models.types import ProviderTrack, MatchConfidence
from tagslut.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("tagslut.metadata.providers.tidal")


class TidalProvider(AbstractProvider):
    """
    Tidal provider.

    Supports:
    - Track by ID: GET /v1/tracks/{id}
    - Text search: GET /v1/search?types=TRACKS&query={query}
    - ISRC search: Client-side filtering on text search results.
    """

    name = "tidal"
    supports_isrc_search = False

    rate_limit_config = RateLimitConfig(
        min_delay=0.4,  # As requested
        max_retries=3,
        base_backoff=2.0,
    )

    BASE_URL = "https://api.tidal.com/v1"
    # Country code for Tidal API requests - configurable via environment variable
    # Default: "US". Override with TIDAL_COUNTRY_CODE env var.
    COUNTRY_CODE = os.environ.get("TIDAL_COUNTRY_CODE", "US")

    def _get_default_headers(self) -> Dict[str, str]:
        """Get headers with Bearer token."""
        token = self._get_token()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if token and token.access_token:
            headers["Authorization"] = f"Bearer {token.access_token}"
        return headers

    def _make_request(self, *args, **kwargs):  # type: ignore  # TODO: mypy-strict
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

        response = self._make_request("GET", url)  # type: ignore  # TODO: mypy-strict
        if response is None or response.status_code != 200:
            logger.warning("Failed to fetch Tidal track %s", track_id)
            return None

        try:
            track = self._normalize_track(response.json())
            if track is None:
                logger.warning("Tidal track %s returned unusable data", track_id)
                return None
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
            "types": "TRACKS",
            "limit": min(limit, 50),
        }

        response = self._make_request("GET", url, params=params)  # type: ignore  # TODO: mypy-strict
        if response is None or response.status_code != 200:
            logger.warning("Tidal search failed for query: %s", query)
            return []

        try:
            data = response.json()
            tracks = data.get("tracks", {}).get("items", [])
            results = []
            for t in tracks:
                normalized = self._normalize_track(t)
                if normalized is not None:
                    results.append(normalized)
            return results
        except Exception as e:
            logger.error("Failed to parse Tidal search response: %s", e)
            return []

    @staticmethod
    def _cover_to_url(cover_id: Optional[str], size: int = 640) -> Optional[str]:
        """Convert Tidal cover UUID to resources image URL."""
        if not cover_id:
            return None
        return f"https://resources.tidal.com/images/{cover_id.replace('-', '/')}/{size}x{size}.jpg"

    def _normalize_track(  # type: ignore  # TODO: mypy-strict
            self, attributes: Dict[str, Any]) -> Optional[ProviderTrack]:
        """
        Normalize Tidal track object to ProviderTrack.

        Returns:
            ProviderTrack if data contains usable fields, None otherwise.
            This avoids returning stub objects that lack meaningful content.
        """
        # Return None for empty/unusable data instead of stub ProviderTrack
        if not attributes:
            logger.debug("Empty attributes received, returning None")
            return None

        # Support both v1 object shape and JSON:API resource wrapper fallback
        if "resource" in attributes and isinstance(attributes.get("resource"), dict):
            attributes = attributes.get("resource", {}).get("attributes", {})

        track_id = attributes.get("id")
        title = attributes.get("title")
        if not title and not track_id:
            logger.debug("Track missing both title and id, returning None")
            return None

        artists = attributes.get("artists", [])
        artist_name = ", ".join(a.get("name", "") for a in artists if a.get("name")) if artists else None

        album = attributes.get("album", {})
        album_name = album.get("title") if isinstance(album, dict) else None

        release_date = None
        if isinstance(album, dict):
            release_date = album.get("releaseDate")
        if not release_date:
            release_date = attributes.get("releaseDate") or attributes.get("streamStartDate")
        year = None
        if release_date:
            try:
                year = int(release_date[:4])
            except (ValueError, IndexError):
                pass

        duration_s = attributes.get("duration")
        duration_ms = duration_s * 1000 if duration_s else None

        key_value = attributes.get("key")
        key_scale = attributes.get("keyScale")
        canonical_key = None
        if key_value and key_scale:
            scale = str(key_scale).upper()
            if scale.startswith("MAJ"):
                canonical_key = f"{key_value} major"
            elif scale.startswith("MIN"):
                canonical_key = f"{key_value} minor"
            else:
                canonical_key = f"{key_value} {str(key_scale).lower()}"
        elif key_value:
            canonical_key = str(key_value)

        explicit = attributes.get("explicit")
        if explicit is None:
            explicit = "EXPLICIT" in (attributes.get("parentalWarningType") or "")

        album_art_url = self._cover_to_url(album.get("cover")) if isinstance(album, dict) else None
        track_url = attributes.get("url")
        if not track_url and track_id is not None:
            track_url = f"https://tidal.com/browse/track/{track_id}"

        return ProviderTrack(
            service="tidal",
            service_track_id=str(track_id),
            title=title,
            artist=artist_name,
            album=album_name,
            duration_ms=duration_ms,
            isrc=attributes.get("isrc"),
            year=year,
            release_date=release_date,
            album_art_url=album_art_url,
            url=track_url,
            track_number=attributes.get("trackNumber"),
            disc_number=attributes.get("volumeNumber"),
            explicit=bool(explicit),
            bpm=attributes.get("bpm"),
            key=canonical_key,
            audio_quality=attributes.get("audioQuality"),
            copyright=attributes.get("copyright"),
            match_confidence=MatchConfidence.NONE,
            raw=attributes,
        )
