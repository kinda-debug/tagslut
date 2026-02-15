"""MusicBrainz provider implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from tagslut.core.models import Album, Artist, Artwork, ProviderInfo, Track

from .base import MusicProvider, ProviderError


class MusicBrainzProvider(MusicProvider):
    """Adapter for the MusicBrainz web service."""

    name = "musicbrainz"
    base_url = "https://musicbrainz.org/ws/2"

    def __init__(self, user_agent: str, *, client=None) -> None:
        if not user_agent:
            raise ProviderError("MusicBrainz requires a user agent")
        super().__init__(client=client)
        self._headers = {"User-Agent": user_agent}

    async def search_track(self, query: str, *, limit: int = 5) -> List[Track]:
        params = {"query": query, "fmt": "json", "limit": limit}
        payload = await self._request(
            "GET",
            f"{self.base_url}/recording",
            params=params,
            headers=self._headers,
        )
        recordings = payload.get("recordings", [])
        tracks = [self._parse_recording(recording) for recording in recordings]
        return self._truncate_results(tracks, limit)

    async def get_track(self, external_id: str) -> Track:
        payload = await self._request(
            "GET",
            f"{self.base_url}/recording/{external_id}",
            params={"fmt": "json", "inc": "releases+artists"},
            headers=self._headers,
        )
        return self._parse_recording(payload)

    async def get_album(self, external_id: str) -> Album:
        payload = await self._request(
            "GET",
            f"{self.base_url}/release/{external_id}",
            params={"fmt": "json", "inc": "artists+recordings+release-groups"},
            headers=self._headers,
        )
        return self._parse_release(payload)

    def _parse_recording(self, data: Dict[str, Any]) -> Track:
        releases = data.get("releases", [])
        album = self._parse_release(releases[0]) if releases else None
        artists = [self._parse_artist(credit) for credit in data.get("artist-credit", [])]
        url = _extract_url(data.get("relations"))
        providers = [self._make_provider_info(external_id=data.get("id"), url=url)]
        return Track(
            title=data.get("title", ""),
            artists=artists,
            album=album,
            duration_ms=int(data.get("length", 0)) if data.get("length") else None,
            track_number=None,
            disc_number=None,
            explicit=False,
            providers=providers,
            isrc=(data.get("isrcs") or [None])[0],
        )

    def _parse_release(self, data: Dict[str, Any]) -> Album:
        artists = [self._parse_artist(credit) for credit in data.get("artist-credit", [])]
        images = data.get("cover-art-archive", {})
        artwork = None
        if images.get("front") and data.get("id"):
            artwork = Artwork(
                url=f"https://coverartarchive.org/release/{data['id']}/front-500",
                mime_type="image/jpeg",
            )
        url = _extract_url(data.get("relations"))
        providers = [self._make_provider_info(external_id=data.get("id"), url=url)]
        return Album(
            title=data.get("title", ""),
            artists=artists,
            release_date=_parse_date(data.get("date")),
            artwork=artwork,
            providers=providers,
        )

    def _parse_artist(self, credit: Any) -> Artist:
        if isinstance(credit, dict):
            name = credit.get("name") or credit.get("artist", {}).get("name", "")
            artist_data = credit.get("artist")
            artist_id = artist_data.get("id") if artist_data else credit.get("id")
        else:
            name = str(credit)
            artist_id = None
        provider = ProviderInfo(name=self.name, external_id=artist_id, url=None)
        return Artist(name=name, providers=[provider])



def _extract_url(relations: Any) -> Optional[str]:
    if not relations:
        return None
    for relation in relations:
        url = relation.get('url', {}).get('resource')
        if url:
            return url
    return None


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


__all__ = ["MusicBrainzProvider"]
