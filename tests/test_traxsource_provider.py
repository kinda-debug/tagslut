"""Unit tests for the Traxsource metadata provider."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import httpx

from tagslut.metadata.models.types import MatchConfidence
from tagslut.metadata.providers.traxsource import TraxsourceProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_provider() -> TraxsourceProvider:
    return TraxsourceProvider(token_manager=None)


def _fake_client(status_code: int = 200, json_data: Any = None) -> MagicMock:
    """Return a mock HTTP client whose .request() returns *json_data*."""
    response = httpx.Response(
        status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://example.com"),
    )
    client = MagicMock()
    client.request.return_value = response
    return client


# ---------------------------------------------------------------------------
# _normalize_track
# ---------------------------------------------------------------------------

MINIMAL_TRACK: dict[str, Any] = {
    "id": 12345,
    "title": "Test Track",
    "version": "Original Mix",
    "artists": [{"id": 1, "name": "DJ Foo"}],
    "label": {"id": 10, "name": "Some Label"},
    "release": {"id": 99, "title": "Test EP", "images": {"large": "https://img.example.com/art.jpg"}},
    "genre": {"id": 5, "name": "House"},
    "bpm": 125,
    "key": "F maj",
    "duration": 360000,
    "isrc": "USABC1234567",
    "publish_date": "2023-06-15",
    "slug": "test-track",
}


def test_normalize_track_basic() -> None:
    provider = _make_provider()
    track = provider._normalize_track(MINIMAL_TRACK)

    assert track.service == "traxsource"
    assert track.service_track_id == "12345"
    assert track.title == "Test Track"          # "Original Mix" stripped from title
    assert track.artist == "DJ Foo"
    assert track.album == "Test EP"
    assert track.album_id == "99"
    assert track.label == "Some Label"
    assert track.genre == "House"
    assert track.bpm == 125.0
    assert track.key == "F maj"
    assert track.duration_ms == 360000
    assert track.isrc == "USABC1234567"
    assert track.year == 2023
    assert track.album_art_url == "https://img.example.com/art.jpg"
    assert track.url == "https://www.traxsource.com/title/12345/test-track"
    assert track.match_confidence == MatchConfidence.NONE


def test_normalize_track_non_original_mix_appended() -> None:
    provider = _make_provider()
    data = {**MINIMAL_TRACK, "version": "Dub Mix"}
    track = provider._normalize_track(data)
    assert track.title == "Test Track (Dub Mix)"
    assert track.mix_name == "Dub Mix"


def test_normalize_track_multiple_artists() -> None:
    provider = _make_provider()
    data = {**MINIMAL_TRACK, "artists": [{"name": "A"}, {"name": "B"}, {"name": "C"}]}
    track = provider._normalize_track(data)
    assert track.artist == "A, B, C"


def test_normalize_track_missing_fields_graceful() -> None:
    provider = _make_provider()
    track = provider._normalize_track({"id": 1})
    assert track.service_track_id == "1"
    assert track.title is None
    assert track.artist is None
    assert track.duration_ms is None
    assert track.bpm is None


# ---------------------------------------------------------------------------
# _extract_tracks_from_payload
# ---------------------------------------------------------------------------

def test_extract_tracks_search_envelope() -> None:
    payload = {
        "results": {
            "TR": {
                "count": 1,
                "items": [{"id": 1, "title": "Track"}],
            }
        }
    }
    rows = TraxsourceProvider._extract_tracks_from_payload(payload)
    assert len(rows) == 1
    assert rows[0]["id"] == 1


def test_extract_tracks_flat_list() -> None:
    payload = [{"id": 1}, {"id": 2}]
    rows = TraxsourceProvider._extract_tracks_from_payload(payload)
    assert len(rows) == 2


def test_extract_tracks_single_dict_with_id() -> None:
    payload = {"id": 99, "title": "Solo"}
    rows = TraxsourceProvider._extract_tracks_from_payload(payload)
    assert rows == [payload]


def test_extract_tracks_top_level_items() -> None:
    payload = {"items": [{"id": 5}, {"id": 6}]}
    rows = TraxsourceProvider._extract_tracks_from_payload(payload)
    assert [r["id"] for r in rows] == [5, 6]


def test_extract_tracks_empty() -> None:
    rows = TraxsourceProvider._extract_tracks_from_payload({})
    assert rows == []


# ---------------------------------------------------------------------------
# fetch_by_id
# ---------------------------------------------------------------------------

def test_fetch_by_id_success(monkeypatch) -> None:
    provider = _make_provider()
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    provider._client = _fake_client(200, MINIMAL_TRACK)

    track = provider.fetch_by_id("12345")
    assert track is not None
    assert track.service_track_id == "12345"
    assert track.match_confidence == MatchConfidence.EXACT


def test_fetch_by_id_not_found(monkeypatch) -> None:
    provider = _make_provider()
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    provider._client = _fake_client(404, {})

    track = provider.fetch_by_id("99999")
    assert track is None


def test_fetch_by_id_bad_json(monkeypatch) -> None:
    provider = _make_provider()
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)

    bad_response = httpx.Response(
        200,
        content=b"not json",
        request=httpx.Request("GET", "https://example.com"),
    )
    client = MagicMock()
    client.request.return_value = bad_response
    provider._client = client

    track = provider.fetch_by_id("12345")
    assert track is None


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

SEARCH_PAYLOAD = {
    "results": {
        "TR": {
            "count": 1,
            "items": [MINIMAL_TRACK],
        }
    }
}


def test_search_returns_tracks(monkeypatch) -> None:
    provider = _make_provider()
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    provider._client = _fake_client(200, SEARCH_PAYLOAD)

    tracks = provider.search("DJ Foo Test Track", limit=5)
    assert len(tracks) == 1
    assert tracks[0].title == "Test Track"


def test_search_empty_on_error(monkeypatch) -> None:
    provider = _make_provider()
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    provider._client = _fake_client(500, {})

    # Exhaust retries by setting consecutive errors above max_retries threshold
    provider.rate_limiter._consecutive_errors = provider.rate_limiter.config.max_retries

    tracks = provider.search("anything")
    assert tracks == []


# ---------------------------------------------------------------------------
# search_by_isrc
# ---------------------------------------------------------------------------

def test_search_by_isrc_match(monkeypatch) -> None:
    provider = _make_provider()
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    provider._client = _fake_client(200, SEARCH_PAYLOAD)

    tracks = provider.search_by_isrc("USABC1234567")
    assert len(tracks) == 1
    assert tracks[0].match_confidence == MatchConfidence.EXACT


def test_search_by_isrc_no_match(monkeypatch) -> None:
    provider = _make_provider()
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    provider._client = _fake_client(200, SEARCH_PAYLOAD)

    tracks = provider.search_by_isrc("ZZZZZZZZZZZZ")
    assert tracks == []


# ---------------------------------------------------------------------------
# Rate limiting integration (mirrors beatport test style)
# ---------------------------------------------------------------------------

def test_traxsource_retries_on_429(monkeypatch) -> None:
    provider = _make_provider()
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    monkeypatch.setattr("tagslut.metadata.providers.base.time.sleep", lambda _: None)

    calls: list[int] = []

    def fake_request(method: str, url: str, headers: dict, params=None, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                request=httpx.Request(method, url),
            )
        return httpx.Response(
            200,
            json=SEARCH_PAYLOAD,
            request=httpx.Request(method, url),
        )

    mock_client = MagicMock()
    mock_client.request.side_effect = lambda method, url, **kw: fake_request(
        method, url, kw.get("headers", {}), kw.get("params")
    )
    provider._client = mock_client

    tracks = provider.search("test")
    assert len(tracks) == 1
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# Enricher registration
# ---------------------------------------------------------------------------

def test_enricher_registers_traxsource(tmp_path) -> None:
    """Enricher._get_provider('traxsource') should return a TraxsourceProvider."""
    from tagslut.metadata.enricher import Enricher

    db = tmp_path / "music.db"
    db.touch()

    with Enricher(db_path=db, providers=["traxsource"]) as enricher:
        provider = enricher._get_provider("traxsource")

    assert isinstance(provider, TraxsourceProvider)
