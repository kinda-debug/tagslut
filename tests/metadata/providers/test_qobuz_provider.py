from __future__ import annotations

from typing import Any

import httpx
import pytest

from tagslut.metadata.models.types import MatchConfidence
from tagslut.metadata.providers.qobuz import QobuzProvider


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
            raise AssertionError(f"Unexpected Qobuz request: {method} {url}")
        route = self.routes[key]
        if callable(route):
            return route(self.calls[-1])
        return route


class _StubTokenManager:
    def __init__(self, *, app_id: str | None = "app", token: str | None = "tok") -> None:
        self._app_id = app_id
        self._token = token

    def get_qobuz_app_credentials(self) -> tuple[str | None, str | None]:
        return (self._app_id, "secret" if self._app_id else None)

    def ensure_qobuz_token(self) -> str | None:
        return self._token


def _make_provider(
    monkeypatch: pytest.MonkeyPatch,
    *,
    routes: dict[tuple[str, str], Any] | None = None,
    token_manager: _StubTokenManager | None = None,
) -> tuple[QobuzProvider, _StubClient]:
    provider = QobuzProvider(token_manager=token_manager)
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    stub = _StubClient(routes or {})
    provider._client = stub  # type: ignore[assignment]
    return provider, stub


def test_normalize_track_maps_fields() -> None:
    provider = QobuzProvider(token_manager=None)
    raw = {
        "id": 123,
        "title": "Example Track",
        "performer": {"name": "The Performer"},
        "artist": {"name": "Ignored Artist"},
        "album": {
            "id": 456,
            "title": "Example Album",
            "release_date_original": "2020-01-02",
            "label": {"name": "Example Label"},
            "image": {"large": "https://img.example/large.jpg"},
        },
        "isrc": "USRC17607839",
        "duration": 245,
        "track_number": 7,
        "version": "Remastered",
        "parental_warning": 1,
        "composer": {"name": "Composer Name"},
        "work": "Ignored Work Field",
    }

    track = provider._normalize_track(raw)
    assert track.service == "qobuz"
    assert track.service_track_id == "123"
    assert track.title == "Example Track"
    assert track.artist == "The Performer"
    assert track.album == "Example Album"
    assert track.album_id == "456"
    assert track.isrc == "USRC17607839"
    assert track.duration_ms == 245000
    assert track.track_number == 7
    assert track.release_date == "2020-01-02"
    assert track.label == "Example Label"
    assert track.version == "Remastered"
    assert track.explicit is True
    assert track.album_art_url == "https://img.example/large.jpg"
    assert track.composer == "Composer Name"
    assert track.url == "https://open.qobuz.com/track/123"


def test_search_by_isrc_filters_results(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, stub = _make_provider(
        monkeypatch,
        token_manager=_StubTokenManager(),
        routes={
            ("GET", "https://www.qobuz.com/api.json/0.2/track/search"): _json_response(
                200,
                {
                    "tracks": {
                        "items": [
                            {"id": 1, "title": "A", "isrc": "USRC17607839", "artist": {"name": "X"}},
                            {"id": 2, "title": "B", "isrc": "NOPE00000000", "artist": {"name": "Y"}},
                        ]
                    }
                },
            ),
        },
    )

    results = provider.search_by_isrc("USRC17607839")
    assert [t.service_track_id for t in results] == ["1"]
    assert results[0].match_confidence == MatchConfidence.EXACT
    assert stub.calls[0]["params"]["query"] == "USRC17607839"
    assert stub.calls[0]["params"]["limit"] == 5


def test_missing_user_auth_token_returns_empty_results(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _make_provider(monkeypatch, token_manager=_StubTokenManager(token=None))
    assert provider.search("anything") == []
    assert provider.search_by_isrc("USRC17607839") == []
    assert provider.fetch_by_id("123") is None
