from __future__ import annotations

from typing import Any

import httpx
import pytest

from tagslut.metadata.models.types import EnrichmentResult, LocalFileInfo, MatchConfidence, ProviderTrack
from tagslut.metadata.pipeline.stages import apply_cascade
from tagslut.metadata.provider_registry import PROVIDER_REGISTRY, ProviderActivationConfig
from tagslut.metadata.providers.reccobeats import ReccoBeatsProvider


def _json_response(status_code: int, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


class _StubClient:
    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "params": params or {},
                "kwargs": kwargs,
            }
        )
        key = (method, url)
        if key not in self.routes:
            raise AssertionError(f"Unexpected ReccoBeats request: {method} {url}")
        route = self.routes[key]
        if callable(route):
            return route(self.calls[-1])
        return route


def _make_provider(
    monkeypatch: pytest.MonkeyPatch,
    routes: dict[tuple[str, str], Any],
) -> tuple[ReccoBeatsProvider, _StubClient]:
    provider = ReccoBeatsProvider(token_manager=None)
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    stub = _StubClient(routes)
    provider._client = stub  # type: ignore[assignment]
    return provider, stub


def test_fetch_by_isrc_returns_audio_features(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, stub = _make_provider(
        monkeypatch,
        {
            ("GET", "https://api.reccobeats.com/v1/track"): _json_response(
                200,
                {
                    "content": [
                        {
                            "id": "c00cbf4f-0000-0000-0000-000000000000",
                            "isrc": "USRC17607839",
                            "trackTitle": "Example",
                        }
                    ]
                },
            ),
            ("GET", "https://api.reccobeats.com/v1/audio-features"): _json_response(
                200,
                {
                    "content": [
                        {
                            "id": "c00cbf4f-0000-0000-0000-000000000000",
                            "isrc": "USRC17607839",
                            "acousticness": 0.204,
                            "danceability": 0.595,
                            "energy": 0.847,
                            "instrumentalness": 0.0,
                            "loudness": -7.934,
                            "tempo": 150.343,
                            "valence": 0.546,
                        }
                    ]
                },
            ),
        },
    )

    track = provider.fetch_by_isrc("USRC17607839")
    assert track is not None
    assert track.match_confidence == MatchConfidence.EXACT
    assert track.isrc == "USRC17607839"
    assert track.energy is not None
    assert track.danceability is not None
    assert track.valence is not None
    assert track.acousticness is not None
    assert track.instrumentalness is not None
    assert track.loudness is not None
    assert track.bpm is not None
    assert stub.calls[0]["params"]["ids"] == "USRC17607839"
    assert stub.calls[1]["params"]["ids"] == "c00cbf4f-0000-0000-0000-000000000000"


def test_fetch_by_isrc_returns_none_when_isrc_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _make_provider(
        monkeypatch,
        {
            ("GET", "https://api.reccobeats.com/v1/track"): _json_response(200, {"content": []}),
        },
    )
    assert provider.fetch_by_isrc("NOHIT0000000") is None


def test_search_returns_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _make_provider(monkeypatch, {})
    assert provider.search("whatever") == []


def test_reccobeats_registered_in_registry() -> None:
    assert "reccobeats" in PROVIDER_REGISTRY


def test_reccobeats_enabled_by_default() -> None:
    cfg = ProviderActivationConfig()
    assert cfg.reccobeats.metadata_enabled is True
    assert cfg.reccobeats.trust == "secondary"


def test_bpm_not_overwritten_by_reccobeats_tempo() -> None:
    beatport = ProviderTrack(service="beatport", service_track_id="bp-1", bpm=128.0, match_confidence=MatchConfidence.EXACT)
    reccobeats = ProviderTrack(service="reccobeats", service_track_id="rb-1", bpm=150.0, match_confidence=MatchConfidence.EXACT)
    result = EnrichmentResult(path="x", matches=[beatport, reccobeats])
    out = apply_cascade(result, LocalFileInfo(path="x"), mode="hoarding")
    assert out.canonical_bpm == 128.0


def test_audio_features_cascade_fills_empty_fields() -> None:
    beatport = ProviderTrack(service="beatport", service_track_id="bp-1", bpm=128.0, match_confidence=MatchConfidence.EXACT)
    reccobeats = ProviderTrack(
        service="reccobeats",
        service_track_id="rb-1",
        match_confidence=MatchConfidence.EXACT,
        energy=0.8,
        danceability=0.6,
        valence=0.5,
        acousticness=0.2,
        instrumentalness=0.0,
        loudness=-8.0,
        bpm=150.0,
    )
    result = EnrichmentResult(path="x", matches=[beatport, reccobeats])
    out = apply_cascade(result, LocalFileInfo(path="x"), mode="hoarding")
    assert out.canonical_energy == 0.8
    assert out.canonical_danceability == 0.6
    assert out.canonical_valence == 0.5
    assert out.canonical_acousticness == 0.2
    assert out.canonical_instrumentalness == 0.0
    assert out.canonical_loudness == -8.0
    assert out.canonical_bpm == 128.0

