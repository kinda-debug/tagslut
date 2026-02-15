"""Tidal provider implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from tagslut.core.models import Album, Artist, Artwork, ProviderInfo, Track

from .base import MusicProvider, ProviderError


class TidalProvider(MusicProvider):
    """Adapter for the Tidal public API endpoints."""

    name = "tidal"
    base_url = "https://api.tidalhifi.com/v1"

    def __init__(
        self,
        token: str,
        session_id: str,
        country_code: str = "US",
        *,
        client=None,
    ) -> None:
        if not token or not session_id:
            raise ProviderError("Tidal provider requires a token and session_id")
        super().__init__(client=client)
        self._token = token
        self._session_id = session_id
        self._country_code = country_code

    async def _get(self, endpoint: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        params = params or {}
        params.setdefault("countryCode", self._country_code)
        headers = {
            "X-Tidal-Token": self._token,
            "sessionId": self._session_id,
        }
        return await self._request(
            "GET", f"{self.base_url}/{endpoint}", params=params, headers=headers
        )

    async def search_track(self, query: str, *, limit: int = 5) -> List[Track]:
        payload = await self._get("search/tracks", params={"query": query, "limit": limit})
        tracks_payload = payload.get("items", [])
        tracks = [self._parse_track(item) for item in tracks_payload]
        return self._truncate_results(tracks, limit)

    async def get_track(self, external_id: str) -> Track:
        payload = await self._get(f"tracks/{external_id}")
        return self._parse_track(payload)

    async def get_album(self, external_id: str) -> Album:
        payload = await self._get(f"albums/{external_id}")
        return self._parse_album(payload)

    def _parse_track(self, data: Dict[str, Any]) -> Track:
        album = self._parse_album(data.get("album", {})) if data.get("album") else None
        artists = [self._parse_artist(artist) for artist in data.get("artists", [])]
        providers = [
            self._make_provider_info(
                external_id=str(data.get("id")),
                url=data.get("url"),
            )
        ]
        release_date = data.get("streamStartDate") or data.get("releaseDate")
        album_release = _parse_date(release_date)
        if album and album_release and not album.release_date:
            album.release_date = album_release
        return Track(
            title=data.get("title", ""),
            artists=artists,
            album=album,
            duration_ms=int(data.get("duration", 0)) * 1000 if data.get("duration") else None,
            track_number=data.get("trackNumber"),
            disc_number=data.get("volumeNumber"),
            explicit=bool(data.get("explicit")),
            providers=providers,
            isrc=data.get("isrc"),
        )

    def _parse_album(self, data: Dict[str, Any]) -> Album:
        artists = []
        if data.get("artists"):
            artists = [self._parse_artist(artist) for artist in data.get("artists", [])]
        image_id = data.get("cover")
        artwork = None
        if image_id:
            artwork = Artwork(
                url=f"https://resources.tidal.com/images/{image_id}/640x640.jpg",
                mime_type="image/jpeg",
            )
        providers = [
            self._make_provider_info(
                external_id=str(data.get("id")),
                url=data.get("url"),
            )
        ]
        return Album(
            title=data.get("title", ""),
            artists=artists,
            release_date=_parse_date(data.get("releaseDate")),
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


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


__all__ = ["TidalProvider"]
