from __future__ import annotations

from typing import Any

from tagslut.dj.key_utils import classical_to_camelot
from tagslut.dj.spotify_key import spotify_key_to_classical
from tagslut.library.matcher import TrackQuery
from tagslut.metadata.auth import TokenManager
from tagslut.metadata.models.types import ProviderTrack
from tagslut.metadata.providers.spotify import SpotifyProvider as _LegacySpotifyProvider

from .base import FieldCandidate, ProviderConfigError, RawResult


class SpotifyProvider:
    name = "spotify"

    def __init__(self, token_manager: TokenManager | None = None) -> None:
        self._token_manager = token_manager or TokenManager()

    def search(self, query: TrackQuery) -> list[RawResult]:
        legacy = self._legacy_provider()

        if query.spotify_id:
            track = legacy.fetch_by_id(query.spotify_id)
            if track is None:
                return []
            return [self._raw_result_from_track(legacy, track, query_text=f"spotify_id:{query.spotify_id}")]

        if query.isrc:
            tracks = legacy.search_by_isrc(query.isrc)
            if tracks:
                return [
                    self._raw_result_from_track(legacy, track, query_text=f"isrc:{query.isrc}")
                    for track in tracks
                ]

        if not query.title and not query.artist:
            return []

        tracks = legacy.search_advanced(
            title=query.title or None,
            artist=query.artist or None,
            limit=10,
        )
        query_text = " ".join(part for part in [query.artist, query.title] if part)
        return [self._raw_result_from_track(legacy, track, query_text=query_text) for track in tracks]

    def normalize(self, raw: RawResult) -> list[FieldCandidate]:
        track_payload = raw.payload.get("track")
        if not isinstance(track_payload, dict):
            return []

        audio_features = raw.payload.get("audio_features")
        if not isinstance(audio_features, dict):
            audio_features = {}

        candidates: list[FieldCandidate] = []
        title = track_payload.get("name")
        if isinstance(title, str) and title.strip():
            candidates.append(self._candidate("canonical_title", title.strip(), 0.98))

        artist_credit = self._artist_credit(track_payload)
        if artist_credit:
            candidates.append(self._candidate("canonical_artist_credit", artist_credit, 0.98))

        album = track_payload.get("album")
        if isinstance(album, dict):
            album_id = album.get("id")
            if isinstance(album_id, str) and album_id.strip():
                candidates.append(self._candidate("canonical_release_id", album_id.strip(), 0.96))

        tempo = audio_features.get("tempo")
        if isinstance(tempo, (int, float)):
            candidates.append(self._candidate("bpm", float(tempo), 0.93))

        spotify_key = self._normalize_key(audio_features)
        if spotify_key is not None:
            candidates.append(self._candidate("musical_key", spotify_key, 0.93))

        energy = self._scaled_percent(audio_features.get("energy"))
        if energy is not None:
            candidates.append(self._candidate("energy", energy, 0.92))

        danceability = self._unit_interval(audio_features.get("danceability"))
        if danceability is not None:
            candidates.append(self._candidate("danceability", danceability, 0.92))

        valence = self._unit_interval(audio_features.get("valence"))
        if valence is not None:
            candidates.append(self._candidate("valence", valence, 0.92))

        spotify_id = track_payload.get("id") or raw.external_id
        if isinstance(spotify_id, str) and spotify_id.strip():
            candidates.append(self._candidate("spotify_id", spotify_id.strip(), 1.0))

        return candidates

    def fetch_playlist_tracks(self, playlist_id: str) -> list[dict[str, Any]]:
        legacy = self._legacy_provider()
        url = f"{legacy.BASE_URL}/playlists/{playlist_id}/tracks"
        params: dict[str, Any] | None = {
            "limit": 100,
            "fields": "items(track(id,name,artists(name),album(id),external_ids(isrc))),next",
        }

        items: list[dict[str, Any]] = []
        while url:
            response = legacy._make_request("GET", url, params=params)
            if response is None or response.status_code != 200:
                raise ProviderConfigError(f"Spotify playlist fetch failed for {playlist_id}")

            payload = response.json()
            for item in payload.get("items", []):
                if not isinstance(item, dict):
                    continue
                track = item.get("track")
                if isinstance(track, dict) and isinstance(track.get("id"), str):
                    items.append(track)

            next_url = payload.get("next")
            url = next_url if isinstance(next_url, str) and next_url else ""
            params = None
        return items

    def _legacy_provider(self) -> _LegacySpotifyProvider:
        if not self._token_manager.is_configured("spotify"):
            raise ProviderConfigError("Spotify credentials are missing")

        token = self._token_manager.get_token("spotify")
        if token is None or token.is_expired:
            token = self._token_manager.refresh_spotify_token()
        if token is None or not token.access_token:
            raise ProviderConfigError("Spotify credentials are invalid")
        return _LegacySpotifyProvider(self._token_manager)

    def _raw_result_from_track(
        self,
        legacy: _LegacySpotifyProvider,
        track: ProviderTrack,
        *,
        query_text: str,
    ) -> RawResult:
        audio_features = None
        if track.service_track_id:
            audio_features = legacy.get_audio_features(track.service_track_id)
        payload = {"track": dict(track.raw), "audio_features": audio_features}
        return RawResult(
            provider=self.name,
            external_id=track.service_track_id or None,
            query_text=query_text,
            payload=payload,
        )

    @staticmethod
    def _artist_credit(track_payload: dict[str, Any]) -> str | None:
        artists = track_payload.get("artists")
        if not isinstance(artists, list):
            return None
        names = [
            str(artist.get("name")).strip()
            for artist in artists
            if isinstance(artist, dict) and artist.get("name")
        ]
        return ", ".join(name for name in names if name) or None

    @staticmethod
    def _normalize_key(audio_features: dict[str, Any]) -> str | None:
        pitch_class = audio_features.get("key")
        mode = audio_features.get("mode")
        if not isinstance(pitch_class, int) or not isinstance(mode, int):
            return None
        classical_key = spotify_key_to_classical(pitch_class, mode)
        return classical_to_camelot(classical_key)

    @staticmethod
    def _scaled_percent(value: Any) -> int | None:
        normalized = SpotifyProvider._unit_interval(value)
        if normalized is None:
            return None
        return int(round(normalized * 100))

    @staticmethod
    def _unit_interval(value: Any) -> float | None:
        if not isinstance(value, (int, float)):
            return None
        normalized = float(value)
        if normalized < 0.0 or normalized > 1.0:
            return None
        return normalized

    def _candidate(self, field_name: str, value: Any, confidence: float) -> FieldCandidate:
        return FieldCandidate(
            field_name=field_name,
            normalized_value=value,
            confidence=confidence,
            rationale={"provider": self.name, "source": "spotify"},
        )
