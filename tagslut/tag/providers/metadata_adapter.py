from __future__ import annotations

from typing import Any, Callable

from tagslut.library.matcher import TrackQuery
from tagslut.metadata.auth import TokenManager
from tagslut.metadata.models.types import MatchConfidence, ProviderTrack
from tagslut.tag.providers.base import FieldCandidate, ProviderConfigError, RawResult


class MetadataServiceTagProvider:
    def __init__(
        self,
        *,
        name: str,
        provider_factory: Callable[[TokenManager | None], Any],
        token_manager: TokenManager | None = None,
        metadata_provider: Any | None = None,
        require_credentials: bool = False,
    ) -> None:
        self.name = name
        self._provider_factory = provider_factory
        self._token_manager = token_manager or TokenManager()
        self._metadata_provider = metadata_provider
        self._require_credentials = require_credentials

    def _provider(self) -> Any:
        if self._metadata_provider is None:
            self._metadata_provider = self._provider_factory(self._token_manager)
        return self._metadata_provider

    def _ensure_configured(self) -> None:
        if not self._require_credentials:
            return
        provider = self._provider()
        ensure_credentials = getattr(provider, "_ensure_credentials", None)
        if callable(ensure_credentials) and ensure_credentials():
            return
        raise ProviderConfigError(
            f"{self.name.capitalize()} credentials are not configured. Run `tagslut auth login {self.name}`."
        )

    @staticmethod
    def _search_text(query: TrackQuery) -> str:
        parts = [query.artist.strip(), query.title.strip()]
        return " - ".join(part for part in parts if part)

    @staticmethod
    def _coalesce_key(track: ProviderTrack) -> str | None:
        for value in (track.key, track.tidal_camelot, track.tidal_key):
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _coalesce_bpm(track: ProviderTrack) -> float | None:
        for value in (track.bpm, track.tidal_bpm):
            if value is not None:
                return float(value)
        return None

    def _serialize_track(self, track: ProviderTrack) -> dict[str, Any]:
        return {
            "service": track.service,
            "service_track_id": track.service_track_id,
            "title": track.title,
            "artist": track.artist,
            "album": track.album,
            "album_id": track.album_id,
            "isrc": track.isrc,
            "url": track.url,
            "duration_ms": track.duration_ms,
            "track_number": track.track_number,
            "disc_number": track.disc_number,
            "year": track.year,
            "release_date": track.release_date,
            "bpm": track.bpm,
            "key": track.key,
            "tidal_bpm": track.tidal_bpm,
            "tidal_key": track.tidal_key,
            "tidal_camelot": track.tidal_camelot,
            "genre": track.genre,
            "sub_genre": track.sub_genre,
            "label": track.label,
            "mix_name": track.mix_name,
            "version": track.version,
            "explicit": track.explicit,
            "match_confidence": track.match_confidence.value,
            "raw": dict(track.raw) if isinstance(track.raw, dict) else {},
        }

    @staticmethod
    def _deserialize_track(payload: dict[str, Any]) -> ProviderTrack:
        confidence_raw = payload.get("match_confidence")
        try:
            confidence = MatchConfidence(str(confidence_raw))
        except ValueError:
            confidence = MatchConfidence.NONE

        return ProviderTrack(
            service=str(payload.get("service") or ""),
            service_track_id=str(payload.get("service_track_id") or ""),
            title=payload.get("title"),
            artist=payload.get("artist"),
            album=payload.get("album"),
            album_id=payload.get("album_id"),
            isrc=payload.get("isrc"),
            url=payload.get("url"),
            duration_ms=payload.get("duration_ms"),
            track_number=payload.get("track_number"),
            disc_number=payload.get("disc_number"),
            year=payload.get("year"),
            release_date=payload.get("release_date"),
            bpm=payload.get("bpm"),
            key=payload.get("key"),
            tidal_bpm=payload.get("tidal_bpm"),
            tidal_key=payload.get("tidal_key"),
            tidal_camelot=payload.get("tidal_camelot"),
            genre=payload.get("genre"),
            sub_genre=payload.get("sub_genre"),
            label=payload.get("label"),
            mix_name=payload.get("mix_name"),
            version=payload.get("version"),
            explicit=payload.get("explicit"),
            match_confidence=confidence,
            raw=payload.get("raw") if isinstance(payload.get("raw"), dict) else {},
        )

    def _field_candidates(self, track: ProviderTrack) -> list[FieldCandidate]:
        candidates: list[FieldCandidate] = []

        def add(field_name: str, value: Any, confidence: float) -> None:
            if value is None:
                return
            if isinstance(value, str) and not value.strip():
                return
            candidates.append(
                FieldCandidate(
                    field_name=field_name,
                    normalized_value=value,
                    confidence=confidence,
                    rationale={
                        "provider": self.name,
                        "external_id": track.service_track_id,
                        "match_confidence": track.match_confidence.value,
                    },
                )
            )

        add("canonical_title", track.title, 0.98)
        add("canonical_artist_credit", track.artist, 0.98)
        add("canonical_album", track.album, 0.90)
        add("canonical_mix_name", track.mix_name or track.version, 0.88)
        add("canonical_label", track.label, 0.90)
        add("canonical_genre", track.genre, 0.86)
        add("canonical_sub_genre", track.sub_genre, 0.84)
        add("canonical_release_date", track.release_date, 0.90)
        add("canonical_explicit", track.explicit, 0.95)
        add("isrc", track.isrc, 0.99)

        bpm = self._coalesce_bpm(track)
        add("bpm", bpm, 0.92)
        add("canonical_bpm", bpm, 0.92)

        key = self._coalesce_key(track)
        add("musical_key", key, 0.90)
        add("canonical_key", key, 0.90)
        return candidates

    def search(self, query: TrackQuery) -> list[RawResult]:
        self._ensure_configured()
        provider = self._provider()

        tracks: list[ProviderTrack] = []
        search_by_isrc = getattr(provider, "search_by_isrc", None)
        if query.isrc and callable(search_by_isrc):
            tracks.extend(search_by_isrc(query.isrc))

        if not tracks:
            text_query = self._search_text(query)
            search = getattr(provider, "search")
            if text_query:
                try:
                    tracks.extend(search(text_query, limit=5))
                except TypeError:
                    tracks.extend(search(text_query))

        seen: set[str] = set()
        query_text = query.isrc or self._search_text(query)
        results: list[RawResult] = []
        for track in tracks:
            external_id = str(track.service_track_id or "").strip()
            if not external_id or external_id in seen:
                continue
            seen.add(external_id)
            results.append(
                RawResult(
                    provider=self.name,
                    external_id=external_id,
                    query_text=query_text,
                    payload=self._serialize_track(track),
                )
            )
        return results

    def normalize(self, raw: RawResult) -> list[FieldCandidate]:
        return self._field_candidates(self._deserialize_track(raw.payload))
