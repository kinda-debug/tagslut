"""
Traxsource public API provider (no token required).

Traxsource is a leading digital download store for house, techno and electronic
music.  Their catalog contains many tracks that are absent from or
under-represented in Beatport.

All endpoints used here are publicly accessible and require no authentication.

API reference / prior art:
  - https://www.traxsource.com
  - OneTagger Traxsource plugin: https://github.com/Marekkon5/onetagger
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from tagslut.metadata.models.types import MatchConfidence, ProviderTrack
from tagslut.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("tagslut.metadata.providers.traxsource")

# Browser-like UA avoids aggressive bot filtering
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/18.0 Safari/605.1.15"
)


class TraxsourceProvider(AbstractProvider):
    """
    Traxsource provider using public search and track endpoints.

    Supports:
    - Text search: GET /api/v1/catalog/search?types=TR&term={query}
    - Track by ID: GET /api/v1/catalog/tracks/{id}
    - ISRC lookup: text-search filtered by ISRC field
    """

    name = "traxsource"
    supports_isrc_search = False  # No dedicated ISRC endpoint; we filter client-side

    rate_limit_config = RateLimitConfig(
        min_delay=1.0,   # Be polite to a smaller store
        max_retries=3,
        base_backoff=2.0,
    )

    BASE_URL = "https://www.traxsource.com/api/v1/catalog"

    def __init__(self, token_manager=None):
        # No credentials needed.
        super().__init__(token_manager=None)

    # ------------------------------------------------------------------
    # AbstractProvider interface
    # ------------------------------------------------------------------

    def _get_default_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        """Fetch a single track by Traxsource track ID."""
        response = self._make_request(
            "GET", f"{self.BASE_URL}/tracks/{track_id}"
        )
        if response is None or response.status_code != 200:
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        track = self._normalize_track(payload)
        track.match_confidence = MatchConfidence.EXACT
        return track

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        """
        Search Traxsource for tracks matching *query*.

        Uses the public catalog search endpoint with ``types=TR`` to restrict
        results to tracks (as opposed to artists/labels/releases).
        """
        params: Dict[str, Any] = {
            "types": "TR",
            "term": query,
            "per_page": max(1, min(limit, 50)),
            "page": 1,
        }
        response = self._make_request(
            "GET",
            f"{self.BASE_URL}/search",
            params=params,
        )
        if response is None or response.status_code != 200:
            return []
        try:
            payload = response.json()
        except Exception:
            return []
        rows = self._extract_tracks_from_payload(payload)
        return [self._normalize_track(r) for r in rows[:limit]]

    def search_by_isrc(self, isrc: str) -> List[ProviderTrack]:
        """
        Search for a track by ISRC.

        Traxsource does not expose a dedicated ISRC endpoint.  We fall back to
        a text search using the ISRC string and then filter results that carry a
        matching ISRC.
        """
        results = self.search(isrc, limit=10)
        exact = [t for t in results if t.isrc and t.isrc.upper() == isrc.upper()]
        if exact:
            for t in exact:
                t.match_confidence = MatchConfidence.EXACT
            return exact
        return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_tracks_from_payload(payload: Any) -> List[Dict[str, Any]]:
        """
        Pull the list of track dicts out of a search response envelope.

        Traxsource wraps results in different structures depending on which
        endpoint is called:

        Search response::

            {
                "results": {
                    "TR": {
                        "count": N,
                        "items": [ {track}, … ]
                    }
                }
            }

        or a flat list / bare dict from the track endpoint.
        """
        if isinstance(payload, list):
            return payload

        # Track-endpoint returns a single dict directly
        if isinstance(payload, dict) and "id" in payload:
            return [payload]

        # Search-envelope shape
        results = payload.get("results") if isinstance(payload, dict) else None
        if isinstance(results, dict):
            # May be under "TR" key
            tr_block = results.get("TR") or results.get("tracks") or results.get("data")
            if isinstance(tr_block, dict):
                items = tr_block.get("items") or tr_block.get("data") or []
                return items if isinstance(items, list) else []
            if isinstance(tr_block, list):
                return tr_block

        # Flat "items" at top level
        items = payload.get("items") if isinstance(payload, dict) else None
        if isinstance(items, list):
            return items

        # "data" at top level
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            return data

        return []

    def _normalize_track(self, data: Dict[str, Any]) -> ProviderTrack:
        """Normalize a Traxsource track dict to :class:`ProviderTrack`."""
        track_id = data.get("id")

        # Title + version/mix name
        title = data.get("title") or data.get("name")
        mix_name = data.get("version") or data.get("mix_name")
        if mix_name and mix_name not in ("Original Mix", "Main Mix"):
            title = f"{title} ({mix_name})" if title else mix_name

        # Artists: list of {id, name, slug} or plain string
        artists_raw = data.get("artists", [])
        if isinstance(artists_raw, list) and artists_raw:
            artist_name = ", ".join(
                a.get("name", "") for a in artists_raw if isinstance(a, dict) and a.get("name")
            ) or None
        elif isinstance(artists_raw, str):
            artist_name = artists_raw or None
        else:
            artist_name = data.get("artist_name") or data.get("artist")

        # Label
        label_raw = data.get("label")
        if isinstance(label_raw, dict):
            label_name = label_raw.get("name") or label_raw.get("label_name")
        else:
            label_name = label_raw or data.get("label_name")

        # Release / album
        release_raw = data.get("release") or data.get("album")
        if isinstance(release_raw, dict):
            album_name = release_raw.get("title") or release_raw.get("name")
            album_id = str(release_raw.get("id")) if release_raw.get("id") is not None else None
            # Image may be a nested dict or a direct URL string
            images = release_raw.get("images") or release_raw.get("image") or {}
            if isinstance(images, dict):
                art_url = (
                    images.get("large")
                    or images.get("medium")
                    or images.get("small")
                    or images.get("url")
                )
            elif isinstance(images, str):
                art_url = images or None
            else:
                art_url = None
        else:
            album_name = None
            album_id = None
            art_url = data.get("image") or data.get("artwork_url")

        # Genre
        genre_raw = data.get("genre") or data.get("genres")
        if isinstance(genre_raw, dict):
            genre_name = genre_raw.get("name") or genre_raw.get("genre_name")
        elif isinstance(genre_raw, list) and genre_raw:
            first = genre_raw[0]
            genre_name = first.get("name") if isinstance(first, dict) else str(first)
        else:
            genre_name = genre_raw if isinstance(genre_raw, str) else None

        # Duration: Traxsource typically stores it in milliseconds
        duration_ms: Optional[int] = None
        raw_duration = data.get("duration") or data.get("length")
        if raw_duration is not None:
            try:
                duration_ms = int(raw_duration)
            except (TypeError, ValueError):
                duration_ms = None

        # BPM
        bpm_val: Optional[float] = None
        if data.get("bpm") is not None:
            try:
                bpm_val = float(data["bpm"])
            except (TypeError, ValueError):
                bpm_val = None

        # Release date / year
        release_date = data.get("publish_date") or data.get("release_date")
        year: Optional[int] = None
        if isinstance(release_date, str) and len(release_date) >= 4:
            try:
                year = int(release_date[:4])
            except ValueError:
                year = None

        # Track URL
        slug = data.get("slug", "")
        if track_id and slug:
            url = f"https://www.traxsource.com/title/{track_id}/{slug}"
        elif track_id:
            url = f"https://www.traxsource.com/title/{track_id}"
        else:
            url = data.get("url")

        return ProviderTrack(
            service="traxsource",
            service_track_id=str(track_id) if track_id is not None else "",
            title=title,
            artist=artist_name,
            album=album_name,
            album_id=album_id,
            duration_ms=duration_ms,
            isrc=data.get("isrc"),
            bpm=bpm_val,
            key=data.get("key") or data.get("key_name"),
            genre=genre_name,
            label=label_name,
            mix_name=mix_name,
            year=year,
            release_date=release_date,
            album_art_url=art_url,
            url=url,
            track_number=data.get("track_number"),
            match_confidence=MatchConfidence.NONE,
            raw=data,
        )
