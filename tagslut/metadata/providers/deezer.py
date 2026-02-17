"""Deezer public API provider (no token required)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from tagslut.metadata.models.types import MatchConfidence, ProviderTrack
from tagslut.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("tagslut.metadata.providers.deezer")


class DeezerProvider(AbstractProvider):
    """Deezer API provider using the public endpoints."""

    name = "deezer"
    supports_isrc_search = True

    rate_limit_config = RateLimitConfig(
        min_delay=0.5,
        max_retries=5,
        base_backoff=5.0,
    )

    BASE_URL = "https://api.deezer.com"

    def __init__(self, token_manager=None):
        # Deezer public API does not require credentials for these endpoints.
        super().__init__(token_manager=None)

    def _get_default_headers(self) -> Dict[str, str]:
        return {"Accept": "application/json"}

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        response = self._make_request("GET", f"{self.BASE_URL}/track/{track_id}")
        if response is None or response.status_code != 200:
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict) or payload.get("error"):
            return None
        track = self._normalize_track(payload)
        track.match_confidence = MatchConfidence.EXACT
        return track

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        response = self._make_request(
            "GET",
            f"{self.BASE_URL}/search",
            params={"q": query, "limit": max(1, min(limit, 100))},
        )
        if response is None or response.status_code != 200:
            return []
        try:
            payload = response.json()
            rows = payload.get("data", []) if isinstance(payload, dict) else []
        except Exception:
            return []
        return [self._normalize_track(r) for r in rows if isinstance(r, dict)]

    def search_by_isrc(self, isrc: str) -> List[ProviderTrack]:
        response = self._make_request("GET", f"{self.BASE_URL}/track/isrc:{isrc}")
        if response is None or response.status_code != 200:
            return []
        try:
            payload = response.json()
        except Exception:
            return []
        if not isinstance(payload, dict) or payload.get("error"):
            return []
        track = self._normalize_track(payload)
        if track.isrc and track.isrc.upper() == isrc.upper():
            track.match_confidence = MatchConfidence.EXACT
            return [track]
        return []

    def _normalize_track(self, data: Dict[str, Any]) -> ProviderTrack:
        artist = data.get("artist") if isinstance(data.get("artist"), dict) else {}
        album = data.get("album") if isinstance(data.get("album"), dict) else {}

        duration_ms = None
        if data.get("duration") is not None:
            try:
                duration_ms = int(float(data.get("duration")) * 1000)
            except Exception:
                duration_ms = None

        bpm_val = None
        if data.get("bpm") is not None:
            try:
                bpm_val = float(data.get("bpm"))
            except Exception:
                bpm_val = None

        release_date = album.get("release_date")
        year = None
        if isinstance(release_date, str) and len(release_date) >= 4:
            try:
                year = int(release_date[:4])
            except Exception:
                year = None

        return ProviderTrack(
            service="deezer",
            service_track_id=str(data.get("id") or ""),
            title=data.get("title") or data.get("title_short"),
            artist=artist.get("name"),
            album=album.get("title"),
            album_id=str(album.get("id")) if album.get("id") is not None else None,
            duration_ms=duration_ms,
            isrc=data.get("isrc"),
            genre=None,
            year=year,
            release_date=release_date,
            bpm=bpm_val,
            album_art_url=(
                album.get("cover_xl")
                or album.get("cover_big")
                or album.get("cover_medium")
                or album.get("cover")
            ),
            url=data.get("link"),
            track_number=data.get("track_position"),
            disc_number=data.get("disk_number"),
            explicit=bool(data.get("explicit_lyrics")) if data.get("explicit_lyrics") is not None else None,
            preview_url=data.get("preview"),
            match_confidence=MatchConfidence.NONE,
            raw=data,
        )
