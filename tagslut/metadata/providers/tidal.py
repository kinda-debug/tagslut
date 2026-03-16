"""
Tidal API provider.

Uses Tidal's v1 API endpoints for search and track lookup.
Authentication is via Bearer token.
"""

import logging
import os
import re
from typing import Optional, List, Dict, Any

from tagslut.metadata.models.types import (
    MatchConfidence,
    ProviderTrack,
    TIDAL_SEED_COLUMNS,
    TidalSeedExportStats,
    TidalSeedRow,
)
from tagslut.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("tagslut.metadata.providers.tidal")
PLAYLIST_ID_PATTERN = re.compile(
    r"^(?:https?://[^/]+/(?:browse/)?playlist/)?(?P<playlist_id>[A-Za-z0-9-]+)(?:[/?#].*)?$"
)


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

    @staticmethod
    def _parse_playlist_id(playlist_url_or_id: str) -> Optional[str]:
        """Extract a playlist identifier from a raw ID or TIDAL playlist URL."""
        candidate = (playlist_url_or_id or "").strip()
        if not candidate:
            return None
        match = PLAYLIST_ID_PATTERN.search(candidate)
        if not match:
            return None
        playlist_id = (match.group("playlist_id") or "").strip()
        return playlist_id or None

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
    def _extract_playlist_items(payload: Dict[str, Any]) -> List[Any]:
        """Extract playlist items from the response payload."""
        items = payload.get("items")
        if isinstance(items, list):
            return items

        data = payload.get("data")
        if isinstance(data, list):
            return data

        tracks = payload.get("tracks")
        if isinstance(tracks, dict):
            track_items = tracks.get("items") or tracks.get("data")
            if isinstance(track_items, list):
                return track_items

        return []

    @staticmethod
    def _extract_next_playlist_url(payload: Dict[str, Any]) -> Optional[str]:
        """Extract the next-page URL from a playlist payload if present."""
        links = payload.get("links")
        if isinstance(links, dict):
            next_link = links.get("next")
            if isinstance(next_link, str) and next_link.strip():
                return next_link.strip()
            if isinstance(next_link, dict):
                href = next_link.get("href")
                if isinstance(href, str) and href.strip():
                    return href.strip()

        next_url = payload.get("next")
        if isinstance(next_url, str) and next_url.strip():
            return next_url.strip()
        return None

    @staticmethod
    def _unwrap_playlist_item(item: Dict[str, Any]) -> Dict[str, Any]:
        """Unwrap a playlist item wrapper down to the track payload if needed."""
        candidate = item
        for key in ("item", "track"):
            nested = candidate.get(key)
            if isinstance(nested, dict):
                candidate = nested
                break

        resource = candidate.get("resource")
        if isinstance(resource, dict):
            attributes = resource.get("attributes")
            if isinstance(attributes, dict):
                flattened = dict(attributes)
                resource_id = resource.get("id")
                if flattened.get("id") is None and resource_id is not None:
                    flattened["id"] = resource_id
                return flattened

        return candidate

    def _seed_row_from_playlist_item(
        self,
        playlist_id: str,
        item: Any,
    ) -> tuple[Optional[TidalSeedRow], Optional[str]]:
        """Convert a playlist item payload into a stable TIDAL seed row."""
        if not isinstance(item, dict):
            logger.debug("Skipping malformed TIDAL playlist item: not a dict")
            return None, "malformed"

        track_payload = self._unwrap_playlist_item(item)
        track = self._normalize_track(track_payload)
        if track is None:
            logger.debug("Skipping unusable TIDAL playlist item: missing normalized track")
            return None, "malformed"
        if not track.service_track_id or not track.title or not track.artist or not track.url:
            logger.debug(
                "Skipping TIDAL playlist item with missing required seed fields: id=%s title=%s artist=%s url=%s",
                track.service_track_id,
                track.title,
                track.artist,
                track.url,
            )
            return None, "missing_required"

        return (
            TidalSeedRow(
                tidal_playlist_id=playlist_id,
                tidal_track_id=track.service_track_id,
                tidal_url=track.url,
                title=track.title,
                artist=track.artist,
                isrc=track.isrc,
            ),
            None,
        )

    def export_playlist_seed_rows(
        self,
        playlist_url_or_id: str,
    ) -> tuple[List[TidalSeedRow], TidalSeedExportStats]:
        """
        Export stable seed rows for a TIDAL playlist.

        This is intentionally narrow and additive: it reuses the existing request
        path and track normalization logic rather than introducing a separate
        playlist client.
        """
        playlist_id = self._parse_playlist_id(playlist_url_or_id)
        if not playlist_id:
            logger.warning("Unable to parse TIDAL playlist identifier from: %s", playlist_url_or_id)
            return [], TidalSeedExportStats(playlist_id=playlist_url_or_id)

        seed_rows: List[TidalSeedRow] = []
        stats = TidalSeedExportStats(playlist_id=playlist_id)
        next_url = f"{self.BASE_URL}/playlists/{playlist_id}/items"
        fallback_url = f"{self.BASE_URL}/playlists/{playlist_id}/tracks"
        params: Optional[Dict[str, Any]] = {"limit": 100, "offset": 0}
        seen_next_urls: set[str] = set()
        seen_row_keys: set[tuple[str, ...]] = set()
        attempted_fallback = False

        while next_url:
            response = self._make_request("GET", next_url, params=params)
            if response is None or response.status_code != 200:
                if not attempted_fallback and next_url.endswith("/items"):
                    attempted_fallback = True
                    stats.endpoint_fallback_used += 1
                    next_url = fallback_url
                    params = {"limit": 100, "offset": 0}
                    continue
                stats.pagination_stop_non_200 += 1
                logger.warning("Failed to fetch TIDAL playlist %s", playlist_id)
                break

            try:
                payload = response.json()
            except Exception as e:
                logger.error("Failed to parse TIDAL playlist response: %s", e)
                break

            stats.pages_fetched += 1
            items = self._extract_playlist_items(payload)
            if not items:
                stats.pagination_stop_empty_page += 1
                break

            for item in items:
                seed_row, skip_reason = self._seed_row_from_playlist_item(playlist_id, item)
                if seed_row is None:
                    if skip_reason == "malformed":
                        stats.malformed_playlist_items += 1
                    elif skip_reason == "missing_required":
                        stats.rows_missing_required_fields += 1
                    continue

                row_key = tuple(str(getattr(seed_row, column) or "") for column in TIDAL_SEED_COLUMNS)
                if row_key in seen_row_keys:
                    stats.duplicate_rows += 1
                    logger.debug(
                        "Skipping duplicate TIDAL seed row: playlist=%s track=%s",
                        seed_row.tidal_playlist_id,
                        seed_row.tidal_track_id,
                    )
                    continue

                seen_row_keys.add(row_key)
                seed_rows.append(seed_row)
                stats.exported_rows += 1
                if not seed_row.isrc:
                    stats.missing_isrc_rows += 1

            next_candidate = self._extract_next_playlist_url(payload)
            if next_candidate:
                if next_candidate.startswith("/"):
                    next_candidate = f"https://api.tidal.com{next_candidate}"
                if next_candidate in seen_next_urls:
                    stats.pagination_stop_repeated_next += 1
                    logger.warning("Stopping TIDAL playlist pagination due to repeated next link: %s", next_candidate)
                    break
                seen_next_urls.add(next_candidate)
                next_url = next_candidate
                params = None
                continue

            if params is None:
                break

            offset = int(params.get("offset", 0))
            limit = int(params.get("limit", 100))
            if len(items) < limit:
                stats.pagination_stop_short_page_no_next += 1
                break
            params = {"limit": limit, "offset": offset + len(items)}

        return seed_rows, stats

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
