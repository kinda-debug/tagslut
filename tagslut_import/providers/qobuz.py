"""Qobuz provider implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from tagslut.core.models import Album, Artist, Artwork, ProviderInfo, Track

from .base import MusicProvider, ProviderError


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse Qobuz release date strings."""

    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class QobuzProvider(MusicProvider):
    """Adapter for the Qobuz JSON API."""

    name = "qobuz"
    base_url = "https://www.qobuz.com/api.json/0.2"

    def __init__(self, app_id: str, app_secret: str, *, client=None) -> None:
        if not app_id or not app_secret:
            raise ProviderError("Qobuz requires both app_id and app_secret")
        super().__init__(client=client)
        self._app_id = app_id
        self._app_secret = app_secret

    async def search_track(self, query: str, *, limit: int = 5) -> List[Track]:
        params = {"app_id": self._app_id, "query": query, "limit": limit}
        payload = await self._request(
            "GET",
            f"{self.base_url}/track/search",
            params=params,
        )
        tracks_payload = payload.get("tracks", {}).get("items", [])
        tracks = [self._parse_track(item) for item in tracks_payload]
        return self._truncate_results(tracks, limit)

    async def get_track(self, external_id: str) -> Track:
        params = {"app_id": self._app_id, "track_id": external_id}
        payload = await self._request("GET", f"{self.base_url}/track/get", params=params)
        return self._parse_track(payload)

    async def get_album(self, external_id: str) -> Album:
        params = {"app_id": self._app_id, "album_id": external_id}
        payload = await self._request("GET", f"{self.base_url}/album/get", params=params)
        return self._parse_album(payload)

    def _parse_track(self, data: Dict[str, Any]) -> Track:
        album_data = data.get("album") or {}
        album = self._parse_album(album_data) if album_data else None
        artists = [self._parse_artist(artist) for artist in data.get("performer", [])]
        if not artists and data.get("artist"):
            artists = [self._parse_artist(data["artist"])]
        providers = [
            self._make_provider_info(
                external_id=str(data.get("id")),
                url=data.get("url"),
            )
        ]
        return Track(
            title=data.get("title", ""),
            artists=artists,
            album=album,
            duration_ms=int(data.get("duration", 0)) * 1000 if data.get("duration") else None,
            track_number=data.get("track_number"),
            disc_number=data.get("media_number"),
            explicit=bool(data.get("parental_warning")),
            providers=providers,
            isrc=data.get("isrc"),
        )

    def _parse_album(self, data: Dict[str, Any]) -> Album:
        artists = []
        if data.get("artist"):
            artists.append(self._parse_artist(data["artist"]))
        images = data.get("image") or {}
        image_url = images.get("large") or images.get("medium") or images.get("small")
        artwork = None
        if image_url:
            artwork = Artwork(url=image_url, mime_type="image/jpeg")
        providers = [
            self._make_provider_info(
                external_id=str(data.get("id")),
                url=data.get("url"),
            )
        ]
        return Album(
            title=data.get("title", ""),
            artists=artists,
            release_date=_parse_date(data.get("released_at")),
            artwork=artwork,
            providers=providers,
        )

    def _parse_artist(self, data: Dict[str, Any]) -> Artist:
        provider = ProviderInfo(
            name=self.name,
            external_id=str(data.get("id")),
            url=data.get("url"),
        )
        return Artist(name=data.get("name", ""), providers=[provider])


__all__ = ["QobuzProvider"]
