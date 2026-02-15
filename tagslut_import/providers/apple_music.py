"""Apple Music provider implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from tagslut.core.models import Album, Artist, Artwork, ProviderInfo, Track

from .base import MusicProvider, ProviderError


class AppleMusicProvider(MusicProvider):
    """Adapter for the Apple Music API."""

    name = "apple_music"
    base_url = "https://api.music.apple.com/v1"

    def __init__(self, developer_token: str, storefront: str = "us", *, client=None) -> None:
        if not developer_token:
            raise ProviderError("Apple Music requires a developer token")
        super().__init__(client=client)
        self._developer_token = developer_token
        self._storefront = storefront

    async def _get(self, endpoint: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        params = params or {}
        headers = {"Authorization": f"Bearer {self._developer_token}"}
        return await self._request(
            "GET", f"{self.base_url}/{endpoint}", params=params, headers=headers
        )

    async def search_track(self, query: str, *, limit: int = 5) -> List[Track]:
        params = {"term": query, "limit": limit, "types": "songs"}
        payload = await self._get(f"catalog/{self._storefront}/search", params=params)
        tracks_payload = payload.get("results", {}).get("songs", {}).get("data", [])
        tracks = [self._parse_track(item) for item in tracks_payload]
        return self._truncate_results(tracks, limit)

    async def get_track(self, external_id: str) -> Track:
        payload = await self._get(f"catalog/{self._storefront}/songs/{external_id}")
        data_list = payload.get("data") or []
        if not data_list:
            raise ProviderError(f"Apple Music track {external_id} not found")
        return self._parse_track(data_list[0])

    async def get_album(self, external_id: str) -> Album:
        payload = await self._get(f"catalog/{self._storefront}/albums/{external_id}")
        data_list = payload.get("data") or []
        if not data_list:
            raise ProviderError(f"Apple Music album {external_id} not found")
        return self._parse_album(data_list[0])

    def _parse_track(self, record: Dict[str, Any]) -> Track:
        attributes = record.get("attributes", {})
        album = None
        relationships = record.get("relationships", {})
        album_data = relationships.get("albums", {}).get("data", [])
        if album_data:
            album = self._parse_album(album_data[0])
        artist_field = attributes.get("artistName", "")
        artists = [self._parse_artist(name) for name in artist_field.split(",") if name]
        providers = [
            self._make_provider_info(
                external_id=record.get("id"),
                url=attributes.get("url"),
            )
        ]
        duration_ms = attributes.get("durationInMillis")
        release_date = _parse_date(attributes.get("releaseDate"))
        if album and release_date and not album.release_date:
            album.release_date = release_date
        return Track(
            title=attributes.get("name", ""),
            artists=artists,
            album=album,
            duration_ms=duration_ms,
            track_number=attributes.get("trackNumber"),
            disc_number=attributes.get("discNumber"),
            explicit=bool(attributes.get("contentRating") == "explicit"),
            providers=providers,
            isrc=attributes.get("isrc"),
        )

    def _parse_album(self, record: Dict[str, Any]) -> Album:
        attributes = record.get("attributes", {})
        artwork_data = attributes.get("artwork", {})
        artwork = None
        url_template = artwork_data.get("url")
        if url_template:
            url = url_template.replace("{w}", "600").replace("{h}", "600")
            artwork = Artwork(url=url, mime_type=artwork_data.get("contentType", "image/jpeg"))
        artists: List[Artist] = []
        artist_name = attributes.get("artistName")
        if artist_name:
            artists.append(self._parse_artist(artist_name))
        providers = [
            self._make_provider_info(
                external_id=record.get("id"),
                url=attributes.get("url"),
            )
        ]
        return Album(
            title=attributes.get("name", ""),
            artists=artists,
            release_date=_parse_date(attributes.get("releaseDate")),
            artwork=artwork,
            providers=providers,
        )

    def _parse_artist(self, data: Any) -> Artist:
        if isinstance(data, dict):
            name = data.get("attributes", {}).get("name") or data.get("name", "")
            external_id = data.get("id")
        else:
            name = str(data)
            external_id = None
        provider = ProviderInfo(name=self.name, external_id=external_id, url=None)
        return Artist(name=name.strip(), providers=[provider])


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


__all__ = ["AppleMusicProvider"]
