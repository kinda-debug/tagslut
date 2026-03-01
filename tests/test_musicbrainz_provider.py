"""Tests for the MusicBrainz metadata provider."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from tagslut.metadata.models.types import MatchConfidence
from tagslut.metadata.providers.musicbrainz import MusicBrainzProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ISRC = "USUM71703861"

_RECORDING: dict[str, Any] = {
    "id": "b84ee12a-09ef-421b-82de-0441a926375b",
    "title": "Shape of You",
    "length": 233713,
    "artist-credit": [
        {"name": "Ed Sheeran", "artist": {"id": "b8a7c51f-362c-4dcb-a259-bc6e0095f0a6", "name": "Ed Sheeran"}},
    ],
    "releases": [
        {
            "id": "4ab58b08-d6c5-4279-be6e-a86c2db55484",
            "title": "÷ (Divide)",
            "date": "2017-03-03",
            "label-info": [{"label": {"name": "Atlantic"}}],
            "media": [{"track": [{"number": "1"}]}],
        }
    ],
    "isrcs": [_ISRC],
}

_ISRC_RESPONSE: dict[str, Any] = {
    "isrc": _ISRC,
    "recordings": [_RECORDING],
}

_SEARCH_RESPONSE: dict[str, Any] = {
    "recordings": [_RECORDING],
    "count": 1,
    "offset": 0,
}


def _make_provider(monkeypatch: pytest.MonkeyPatch, response_data: Any, status_code: int = 200) -> MusicBrainzProvider:
    """Create a provider whose HTTP client returns *response_data* as JSON."""
    provider = MusicBrainzProvider()

    # Skip rate-limit sleep
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)

    class _FakeClient:
        def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
            return httpx.Response(
                status_code,
                content=json.dumps(response_data).encode(),
                headers={"Content-Type": "application/json"},
            )

    provider._client = _FakeClient()  # type: ignore[assignment]
    return provider


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_search_by_isrc_returns_exact_match(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _make_provider(monkeypatch, _ISRC_RESPONSE)
    results = provider.search_by_isrc(_ISRC)

    assert len(results) == 1
    track = results[0]
    assert track.service == "musicbrainz"
    assert track.isrc == _ISRC
    assert track.match_confidence == MatchConfidence.EXACT
    assert track.title == "Shape of You"
    assert track.artist == "Ed Sheeran"
    assert track.duration_ms == 233713
    assert track.year == 2017
    assert track.label == "Atlantic"
    assert track.album == "÷ (Divide)"
    assert track.track_number == 1


def test_search_returns_tracks(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _make_provider(monkeypatch, _SEARCH_RESPONSE)
    results = provider.search("Ed Sheeran Shape of You", limit=5)

    assert len(results) == 1
    track = results[0]
    assert track.title == "Shape of You"
    assert track.match_confidence == MatchConfidence.NONE  # set by caller


def test_fetch_by_id_returns_exact_match(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _make_provider(monkeypatch, _RECORDING)
    track = provider.fetch_by_id("b84ee12a-09ef-421b-82de-0441a926375b")

    assert track is not None
    assert track.match_confidence == MatchConfidence.EXACT
    assert track.service_track_id == "b84ee12a-09ef-421b-82de-0441a926375b"
    assert track.url == "https://musicbrainz.org/recording/b84ee12a-09ef-421b-82de-0441a926375b"


def test_search_by_isrc_http_error_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _make_provider(monkeypatch, {}, status_code=404)
    results = provider.search_by_isrc(_ISRC)
    assert results == []


def test_search_http_error_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _make_provider(monkeypatch, {}, status_code=503)
    results = provider.search("anything")
    assert results == []


def test_fetch_by_id_http_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _make_provider(monkeypatch, {}, status_code=404)
    result = provider.fetch_by_id("missing-mbid")
    assert result is None


def test_normalize_track_missing_optional_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider should tolerate recordings with minimal data."""
    minimal: dict[str, Any] = {"id": "abc123", "title": "Unknown Track"}
    provider = _make_provider(monkeypatch, {"recordings": [minimal]})
    results = provider.search("query")

    assert len(results) == 1
    track = results[0]
    assert track.title == "Unknown Track"
    assert track.artist is None
    assert track.duration_ms is None
    assert track.year is None
    assert track.isrc is None


def test_multiple_artist_credits_joined(monkeypatch: pytest.MonkeyPatch) -> None:
    recording: dict[str, Any] = {
        "id": "multi",
        "title": "Collab Track",
        "artist-credit": [
            {"name": "Artist A", "artist": {"name": "Artist A"}},
            {"name": "Artist B", "artist": {"name": "Artist B"}},
        ],
    }
    provider = _make_provider(monkeypatch, {"recordings": [recording]})
    results = provider.search("query")

    assert len(results) == 1
    assert results[0].artist == "Artist A & Artist B"
