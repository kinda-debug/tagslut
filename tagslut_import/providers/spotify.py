"""Spotify provider implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional

from tagslut.core.models import Album, Artist, Artwork, ProviderInfo, Track

from .base import MusicProvider, ProviderError

TokenGetter = Callable[[], Awaitable[str] | str]


async def _ensure_awaitable(value: Awaitable[str] | str) -> str:
    """Return the awaited value when ``value`` is awaitable."""

    if hasattr(value, "__await__"):
        return await value  # type: ignore[return-value]
    return str(value)


def _parse_release_date(value: Optional[str]) -> Optional[datetime]:
    """Attempt to parse a release date returned by Spotify."""

    if not value:
        return None
    try:
        if len(value) == 4:
            return datetime.fromisoformat(f"{value}-01-01")
        if len(value) == 7:
            return datetime.fromisoformat(f"{value}-01")
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class SpotifyProvider(MusicProvider):
    """Spotify implementation using the official REST API."""

    name = "spotify"
    base_url = "https://api.spotify.com/v1"

    def __init__(self, token_getter: TokenGetter, *, client=None) -> None:
        super().__init__(client=client)
        self._token_getter = token_getter

    async def _headers(self) -> Dict[str, str]:
        token = await _ensure_awaitable(self._token_getter())
        if not token:
            raise ProviderError("Spotify token getter returned an empty token")
        return {"Authorization": f"Bearer {token}"}

    async def search_track(self, query: str, *, limit: int = 5) -> List[Track]:
        params = {"q": query, "type": "track", "limit": limit}
        payload = await self._request(
            "GET",
            f"{self.base_url}/search",
            params=params,
            headers=await self._headers(),
        )
        tracks_payload = payload.get("tracks", {}).get("items", [])
        tracks = [self._parse_track(item) for item in tracks_payload]
        return self._truncate_results(tracks, limit)

    async def get_track(self, external_id: str) -> Track:
        payload = await self._request(
            "GET",
            f"{self.base_url}/tracks/{external_id}",
            headers=await self._headers(),
        )
        return self._parse_track(payload)

    async def get_album(self, external_id: str) -> Album:
        payload = await self._request(
            "GET",
            f"{self.base_url}/albums/{external_id}",
            headers=await self._headers(),
        )
        return self._parse_album(payload)

    def _parse_track(self, data: Dict[str, Any]) -> Track:
        album = self._parse_album(data.get("album", {})) if data.get("album") else None
        artists = [self._parse_artist(artist) for artist in data.get("artists", [])]
        providers = [
            self._make_provider_info(
                external_id=data.get("id"),
                url=(data.get("external_urls") or {}).get("spotify"),
            )
        ]
        return Track(
            title=data.get("name", ""),
            artists=artists,
            album=album,
            duration_ms=data.get("duration_ms"),
            track_number=data.get("track_number"),
            disc_number=data.get("disc_number"),
            explicit=bool(data.get("explicit", False)),
            providers=providers,
            isrc=(data.get("external_ids") or {}).get("isrc"),
        )

    def _parse_album(self, data: Dict[str, Any]) -> Album:
        artists = [self._parse_artist(artist) for artist in data.get("artists", [])]
        images = data.get("images", [])
        artwork = None
        if images:
            image = images[0]
            image_url = image.get("url")
            if image_url:
                artwork = Artwork(
                    url=image_url,
                    width=image.get("width"),
                    height=image.get("height"),
                    mime_type="image/jpeg",
                )
        providers = [
            self._make_provider_info(
                external_id=data.get("id"),
                url=(data.get("external_urls") or {}).get("spotify"),
            )
        ]
        return Album(
            title=data.get("name", ""),
            artists=artists,
            release_date=_parse_release_date(data.get("release_date")),
            artwork=artwork,
            providers=providers,
        )

    def _parse_artist(self, data: Dict[str, Any]) -> Artist:
        provider = ProviderInfo(
            name=self.name,
            external_id=data.get("id"),
            url=(data.get("external_urls") or {}).get("spotify"),
        )
        return Artist(name=data.get("name", ""), providers=[provider])


__all__ = ["SpotifyProvider"]
