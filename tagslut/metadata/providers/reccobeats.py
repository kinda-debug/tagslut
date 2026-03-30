"""ReccoBeats audio feature provider."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from tagslut.metadata.capabilities import Capability
from tagslut.metadata.models.types import MatchConfidence, ProviderTrack
from tagslut.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("tagslut.metadata.providers.reccobeats")


def _as_float(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


class ReccoBeatsProvider(AbstractProvider):
    """
    ReccoBeats audio feature provider.

    Two-step lookup:
    1. /v1/track?ids={isrc}  → resolve ISRC to internal UUID
    2. /v1/audio-features?ids={uuid} → fetch audio features

    No auth required. Free public API.
    """

    BASE_URL = "https://api.reccobeats.com/v1"

    name = "reccobeats"
    supports_isrc_search = True
    rate_limit_config = RateLimitConfig(min_delay=0.3)
    capabilities = {
        Capability.METADATA_FETCH_TRACK_BY_ID,  # treat "by ID" as "by ISRC"
        Capability.METADATA_SEARCH_BY_ISRC,
    }

    def _get_default_headers(self) -> Dict[str, str]:
        return {"Accept": "application/json"}

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        return self.fetch_by_isrc(track_id)

    def fetch_by_isrc(self, isrc: str) -> Optional[ProviderTrack]:
        isrc_norm = (isrc or "").strip().upper()
        if not isrc_norm:
            return None

        track_response = self._make_request(
            "GET",
            f"{self.BASE_URL}/track",
            params={"ids": isrc_norm},
        )
        if track_response is None:
            return None

        try:
            track_payload = track_response.json()
        except Exception:
            logger.debug("reccobeats: malformed JSON for track lookup (isrc=%s)", isrc_norm)
            return None

        content = track_payload.get("content") if isinstance(track_payload, dict) else None
        if not isinstance(content, list):
            return None

        track_entry: dict[str, Any] | None = None
        for entry in content:
            if not isinstance(entry, dict):
                continue
            entry_isrc = str(entry.get("isrc", "")).strip().upper()
            if entry_isrc == isrc_norm:
                track_entry = entry
                break
        if not track_entry:
            return None

        track_uuid = str(track_entry.get("id", "")).strip()
        if not track_uuid:
            return None

        features_response = self._make_request(
            "GET",
            f"{self.BASE_URL}/audio-features",
            params={"ids": track_uuid},
        )
        if features_response is None:
            return None

        try:
            features_payload = features_response.json()
        except Exception:
            logger.debug("reccobeats: malformed JSON for audio features (id=%s)", track_uuid)
            return None

        features_content = features_payload.get("content") if isinstance(features_payload, dict) else None
        if not isinstance(features_content, list):
            return None

        features_entry: dict[str, Any] | None = None
        for entry in features_content:
            if not isinstance(entry, dict):
                continue
            entry_id = str(entry.get("id", "")).strip()
            if entry_id == track_uuid:
                features_entry = entry
                break
        if not features_entry:
            return None

        track = ProviderTrack(
            service=self.name,
            service_track_id=track_uuid,
            isrc=isrc_norm,
            bpm=_as_float(features_entry.get("tempo")),
            acousticness=_as_float(features_entry.get("acousticness")),
            danceability=_as_float(features_entry.get("danceability")),
            energy=_as_float(features_entry.get("energy")),
            instrumentalness=_as_float(features_entry.get("instrumentalness")),
            loudness=_as_float(features_entry.get("loudness")),
            valence=_as_float(features_entry.get("valence")),
            match_confidence=MatchConfidence.EXACT,
            raw={
                "_track": track_entry,
                "_audio_features": features_entry,
            },
        )
        return track

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        logger.debug("reccobeats: search stub (query=%s limit=%d)", query, limit)
        return []

    def search_by_isrc(self, isrc: str) -> List[ProviderTrack]:
        track = self.fetch_by_isrc(isrc)
        return [track] if track else []

