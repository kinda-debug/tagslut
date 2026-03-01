"""
MusicBrainz metadata provider (no authentication required).

API Reference: https://musicbrainz.org/doc/MusicBrainz_API

Supports:
- ISRC lookup: GET /isrc/{isrc}?inc=artist-credits+releases&fmt=json
- Text search: GET /recording?query={query}&limit={n}&fmt=json
- Rate limit: 1 req/sec (enforced via RateLimitConfig min_delay=1.0)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from tagslut.metadata.models.types import MatchConfidence, ProviderTrack
from tagslut.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("tagslut.metadata.providers.musicbrainz")

# User-Agent required by MusicBrainz policy: https://musicbrainz.org/doc/MusicBrainz_API/Rate_Limiting
_USER_AGENT = "tagslut/2.0 ( https://github.com/tagslut/tagslut )"


class MusicBrainzProvider(AbstractProvider):
    """
    MusicBrainz metadata provider.

    Free, unauthenticated API with excellent ISRC coverage.
    Acts as a last-resort fallback after Beatport, Tidal, Deezer, and Traxsource.
    """

    name = "musicbrainz"
    supports_isrc_search = True

    rate_limit_config = RateLimitConfig(
        min_delay=1.0,  # MusicBrainz enforces 1 req/sec
        max_retries=3,
        base_backoff=2.0,
    )

    BASE_URL = "https://musicbrainz.org/ws/2"

    def __init__(self, token_manager: Any = None) -> None:
        # MusicBrainz does not require authentication.
        super().__init__(token_manager=None)

    def _get_default_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }

    # ------------------------------------------------------------------
    # AbstractProvider interface
    # ------------------------------------------------------------------

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        """
        Fetch a MusicBrainz recording by MBID.

        Args:
            track_id: MusicBrainz Recording MBID (UUID)

        Returns:
            ProviderTrack with match_confidence=EXACT, or None if not found.
        """
        url = f"{self.BASE_URL}/recording/{track_id}"
        response = self._make_request(
            "GET",
            url,
            params={"inc": "artist-credits releases", "fmt": "json"},
        )
        if response is None or response.status_code != 200:
            return None
        try:
            data = response.json()
        except Exception:
            return None
        if not isinstance(data, dict) or "id" not in data:
            return None
        track = self._normalize_track(data)
        track.match_confidence = MatchConfidence.EXACT
        return track

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        """
        Search for recordings by text query.

        Args:
            query: Search string (typically "artist title")
            limit: Maximum results to return

        Returns:
            List of ProviderTrack objects
        """
        url = f"{self.BASE_URL}/recording"
        response = self._make_request(
            "GET",
            url,
            params={"query": query, "limit": max(1, min(limit, 100)), "fmt": "json"},
        )
        if response is None or response.status_code != 200:
            return []
        try:
            data = response.json()
            recordings = data.get("recordings", []) if isinstance(data, dict) else []
        except Exception:
            return []
        return [self._normalize_track(r) for r in recordings if isinstance(r, dict)]

    def search_by_isrc(self, isrc: str) -> List[ProviderTrack]:
        """
        Look up recordings by ISRC.

        Args:
            isrc: International Standard Recording Code

        Returns:
            List of ProviderTrack objects with match_confidence=EXACT
        """
        url = f"{self.BASE_URL}/isrc/{isrc}"
        response = self._make_request(
            "GET",
            url,
            params={"inc": "artist-credits releases", "fmt": "json"},
        )
        if response is None or response.status_code != 200:
            return []
        try:
            data = response.json()
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        recordings = data.get("recordings", [])
        results: List[ProviderTrack] = []
        for recording in recordings:
            if not isinstance(recording, dict):
                continue
            track = self._normalize_track(recording)
            track.isrc = isrc  # confirmed by the lookup endpoint
            track.match_confidence = MatchConfidence.EXACT
            results.append(track)
        return results

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    def _normalize_track(self, data: Dict[str, Any]) -> ProviderTrack:
        """
        Normalise a MusicBrainz recording dict to ProviderTrack.

        Recording structure (abbreviated):
        {
          "id": "<mbid>",
          "title": "...",
          "length": 240000,          # milliseconds (may be absent)
          "artist-credit": [
            {"artist": {"id": "...", "name": "..."}, "name": "..."},
            ...
          ],
          "releases": [
            {
              "id": "...",
              "title": "...",
              "date": "YYYY-MM-DD",
              "label-info": [{"label": {"name": "..."}}],
              "track-count": 12,
              "media": [{"track": [{"number": "3"}]}],
            }
          ],
          "isrcs": ["<ISRC>"],
        }
        """
        mbid: str = data.get("id", "")

        # Artist: join all credited names with " & "
        artist: Optional[str] = None
        artist_credits = data.get("artist-credit", [])
        if isinstance(artist_credits, list) and artist_credits:
            parts: List[str] = []
            for credit in artist_credits:
                if isinstance(credit, dict):
                    credited_name = credit.get("name") or credit.get("artist", {}).get("name")
                    if credited_name:
                        parts.append(credited_name)
            if parts:
                artist = " & ".join(parts)

        # Duration: MusicBrainz stores length in milliseconds
        duration_ms: Optional[int] = None
        raw_length = data.get("length")
        if raw_length is not None:
            try:
                duration_ms = int(raw_length)
            except (TypeError, ValueError):
                duration_ms = None

        # Release info: use the first release
        album: Optional[str] = None
        album_id: Optional[str] = None
        year: Optional[int] = None
        release_date: Optional[str] = None
        label: Optional[str] = None
        track_number: Optional[int] = None

        releases = data.get("releases", [])
        if isinstance(releases, list) and releases:
            release = releases[0]
            if isinstance(release, dict):
                album = release.get("title")
                album_id = release.get("id")
                release_date = release.get("date")
                if isinstance(release_date, str) and len(release_date) >= 4:
                    try:
                        year = int(release_date[:4])
                    except (ValueError, TypeError):
                        year = None

                # Label from label-info list
                label_info = release.get("label-info", [])
                if isinstance(label_info, list) and label_info:
                    first_label = label_info[0]
                    if isinstance(first_label, dict):
                        lbl = first_label.get("label") or {}
                        label = lbl.get("name")

                # Track number from media > track
                media = release.get("media", [])
                if isinstance(media, list) and media:
                    tracks = media[0].get("track", [])
                    if isinstance(tracks, list) and tracks:
                        raw_num = tracks[0].get("number")
                        if raw_num is not None:
                            try:
                                track_number = int(raw_num)
                            except (TypeError, ValueError):
                                track_number = None

        # ISRC: recordings may have a list of ISRCs
        isrc: Optional[str] = None
        isrcs = data.get("isrcs", [])
        if isinstance(isrcs, list) and isrcs:
            isrc = isrcs[0]

        url: Optional[str] = f"https://musicbrainz.org/recording/{mbid}" if mbid else None

        return ProviderTrack(
            service="musicbrainz",
            service_track_id=mbid,
            title=data.get("title"),
            artist=artist,
            album=album,
            album_id=album_id,
            isrc=isrc,
            url=url,
            duration_ms=duration_ms,
            track_number=track_number,
            year=year,
            release_date=release_date,
            label=label,
            match_confidence=MatchConfidence.NONE,
            raw=data,
        )
