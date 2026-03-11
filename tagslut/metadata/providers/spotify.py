# DEPRECATED: This script's tagging behavior is superseded by
# `tagslut tag fetch --provider spotify`. This file will be removed
# in a future cleanup pass.

"""
Spotify API provider.

Spotify has the best ISRC support among providers, making it ideal for
track identification. Uses the Web API with client credentials flow.

API Reference: https://developer.spotify.com/documentation/web-api
"""

import logging
from typing import Optional, List, Dict, Any

from tagslut.metadata.models.types import ProviderTrack, MatchConfidence
from tagslut.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("tagslut.metadata.providers.spotify")


class SpotifyProvider(AbstractProvider):
    """
    Spotify Web API provider.

    Supports:
    - Track by ID: GET /v1/tracks/{id}
    - ISRC search: GET /v1/search?q=isrc:{isrc}&type=track (native support!)
    - Text search: GET /v1/search?q={query}&type=track
    """

    name = "spotify"
    supports_isrc_search = True

    rate_limit_config = RateLimitConfig(
        min_delay=0.4,  # Spotify allows ~180 req/min
        max_retries=3,
        base_backoff=2.0,
    )

    BASE_URL = "https://api.spotify.com/v1"

    def _get_default_headers(self) -> Dict[str, str]:
        """Get headers with Bearer token."""
        token = self._get_token()
        headers = {
            "Accept": "application/json",
        }
        if token and token.access_token:
            headers["Authorization"] = f"Bearer {token.access_token}"
        return headers

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        """
        Fetch track by Spotify ID.

        Args:
            track_id: Spotify track ID (e.g., "4cOdK2wGLETKBW3PvgPWqT")

        Returns:
            ProviderTrack with match_confidence=EXACT, or None
        """
        url = f"{self.BASE_URL}/tracks/{track_id}"

        response = self._make_request("GET", url)
        if response is None or response.status_code != 200:
            logger.warning("Failed to fetch Spotify track %s", track_id)
            return None

        try:
            data = response.json()
            track = self._normalize_track(data)
            track.match_confidence = MatchConfidence.EXACT
            return track
        except Exception as e:
            logger.error("Failed to parse Spotify response: %s", e)
            return None

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        """
        Search for tracks by text query.

        Args:
            query: Search query (e.g., "artist title" or "Born Slippy Underworld")
            limit: Maximum results (max 50)

        Returns:
            List of ProviderTrack objects
        """
        url = f"{self.BASE_URL}/search"
        params = {
            "q": query,
            "type": "track",
            "limit": min(limit, 50),
        }

        response = self._make_request("GET", url, params=params)
        if response is None or response.status_code != 200:
            logger.warning("Spotify search failed for query: %s", query)
            return []

        try:
            data = response.json()
            tracks = data.get("tracks", {}).get("items", [])
            return [self._normalize_track(t) for t in tracks]
        except Exception as e:
            logger.error("Failed to parse Spotify search response: %s", e)
            return []

    def search_by_isrc(self, isrc: str) -> List[ProviderTrack]:
        """
        Search by ISRC (native Spotify support).

        Spotify has first-class ISRC search: q=isrc:{ISRC}

        Args:
            isrc: International Standard Recording Code

        Returns:
            List of matching tracks (usually 1 or few)
        """
        url = f"{self.BASE_URL}/search"
        params = {
            "q": f"isrc:{isrc}",
            "type": "track",
            "limit": 10,
        }

        response = self._make_request("GET", url, params=params)
        if response is None or response.status_code != 200:
            logger.warning("Spotify ISRC search failed for: %s", isrc)
            return []

        try:
            data = response.json()
            tracks = data.get("tracks", {}).get("items", [])
            results = []
            for t in tracks:
                track = self._normalize_track(t)
                # Verify ISRC matches (Spotify should return exact matches)
                if track.isrc and track.isrc.upper() == isrc.upper():
                    track.match_confidence = MatchConfidence.EXACT
                results.append(track)
            return results
        except Exception as e:
            logger.error("Failed to parse Spotify ISRC search response: %s", e)
            return []

    def search_advanced(
        self,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        year: Optional[int] = None,
        limit: int = 10,
    ) -> List[ProviderTrack]:
        """
        Advanced search with specific field filters.

        Spotify supports field filters in the query:
        - track:{title}
        - artist:{artist}
        - album:{album}
        - year:{year}

        Args:
            title: Track title
            artist: Artist name
            album: Album name
            year: Release year
            limit: Maximum results

        Returns:
            List of ProviderTrack objects
        """
        query_parts = []
        if title:
            query_parts.append(f'track:"{title}"')
        if artist:
            query_parts.append(f'artist:"{artist}"')
        if album:
            query_parts.append(f'album:"{album}"')
        if year:
            query_parts.append(f"year:{year}")

        if not query_parts:
            return []

        query = " ".join(query_parts)
        return self.search(query, limit=limit)

    def _normalize_track(self, data: Dict[str, Any]) -> ProviderTrack:
        """
        Normalize Spotify track object to ProviderTrack.

        Spotify track structure:
        {
            "id": "...",
            "name": "...",
            "artists": [{"name": "..."}],
            "album": {"name": "...", "release_date": "...", "images": [...]},
            "duration_ms": 123456,
            "external_ids": {"isrc": "..."},
            "explicit": true/false,
            "track_number": 1,
            "disc_number": 1,
            "external_urls": {"spotify": "..."}
        }
        """
        # Extract artist names
        artists = data.get("artists", [])
        artist_name = ", ".join(a.get("name", "") for a in artists) if artists else None

        # Extract album info
        album_data = data.get("album", {})
        album_name = album_data.get("name")
        release_date = album_data.get("release_date", "")

        # Parse year from release_date (can be "YYYY", "YYYY-MM", or "YYYY-MM-DD")
        year = None
        if release_date:
            try:
                year = int(release_date[:4])
            except (ValueError, IndexError):
                pass

        # Get best album art
        images = album_data.get("images", [])
        album_art_url = images[0].get("url") if images else None

        # Get ISRC
        external_ids = data.get("external_ids", {})
        isrc = external_ids.get("isrc")

        # Build track URL
        external_urls = data.get("external_urls", {})
        track_url = external_urls.get("spotify")

        # Get label from album (if available in full album data)
        label = album_data.get("label")

        return ProviderTrack(
            service="spotify",
            service_track_id=data.get("id", ""),
            title=data.get("name"),
            artist=artist_name,
            album=album_name,
            album_id=album_data.get("id"),
            duration_ms=data.get("duration_ms"),
            isrc=isrc,
            bpm=None,  # Requires separate audio-features call
            key=None,  # Requires separate audio-features call
            genre=None,  # Genre is on artist, not track
            label=label,
            year=year,
            release_date=release_date,
            album_art_url=album_art_url,
            url=track_url,
            preview_url=data.get("preview_url"),
            track_number=data.get("track_number"),
            disc_number=data.get("disc_number"),
            explicit=data.get("explicit"),
            popularity=data.get("popularity"),
            match_confidence=MatchConfidence.NONE,  # Set by caller
            raw=data,
        )

    def get_audio_features(self, track_id: str) -> Optional[Dict[str, Any]]:
        """
        Get audio features (BPM, key, etc.) for a track.

        Note: This requires additional API call and scope.

        Returns dict with:
        - tempo: BPM
        - key: Pitch class (0-11, where 0=C)
        - mode: Major (1) or minor (0)
        - time_signature: Beats per bar
        - energy, danceability, etc.
        """
        url = f"{self.BASE_URL}/audio-features/{track_id}"

        response = self._make_request("GET", url)
        if response is None or response.status_code != 200:
            return None

        try:
            return response.json()  # type: ignore  # TODO: mypy-strict
        except Exception:
            return None

    def enrich_with_audio_features(self, track: ProviderTrack) -> ProviderTrack:
        """
        Enrich a track with audio features (BPM, key, energy, etc.).

        Modifies the track in place and returns it.
        """
        if not track.service_track_id:
            return track

        features = self.get_audio_features(track.service_track_id)
        if features:
            # Core DJ features
            track.bpm = features.get("tempo")
            track.time_signature = features.get("time_signature")
            track.mode = features.get("mode")

            # Convert key from pitch class to musical notation
            key_num = features.get("key")
            mode = features.get("mode")
            if key_num is not None and mode is not None:
                track.key = self._pitch_class_to_key(key_num, mode)

            # Audio analysis features (0.0 - 1.0 scale)
            track.energy = features.get("energy")
            track.danceability = features.get("danceability")
            track.valence = features.get("valence")
            track.acousticness = features.get("acousticness")
            track.instrumentalness = features.get("instrumentalness")
            track.liveness = features.get("liveness")
            track.speechiness = features.get("speechiness")
            track.loudness = features.get("loudness")  # dB

        return track

    @staticmethod
    def _pitch_class_to_key(pitch_class: int, mode: int) -> str:
        """
        Convert Spotify pitch class and mode to musical key notation.

        pitch_class: 0=C, 1=C#, 2=D, ... 11=B
        mode: 1=major, 0=minor
        """
        notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        if 0 <= pitch_class < len(notes):
            note = notes[pitch_class]
            suffix = "m" if mode == 0 else ""
            return f"{note}{suffix}"
        return ""
