from __future__ import annotations

import httpx

from tagslut.intake.songlink import resolve_spotify_to_tidal


def _response(status_code: int, payload: object | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://api.song.link/v1-alpha.1/links")
    if payload is None:
        return httpx.Response(status_code=status_code, request=request)
    return httpx.Response(status_code=status_code, json=payload, request=request)


def test_resolve_spotify_to_tidal_extracts_ids(monkeypatch) -> None:
    payload = {
        "entitiesByUniqueId": {
            "SPOTIFY_SONG::abc": {"isrc": "USRC17607839"},
            "TIDAL_SONG::123456": {"id": "123456"},
            "QOBUZ_SONG::987654": {"id": "987654"},
        }
    }

    def fake_get(*_args, **_kwargs):
        return _response(200, payload)

    monkeypatch.setattr("tagslut.intake.songlink.httpx.get", fake_get)

    resolved = resolve_spotify_to_tidal("https://open.spotify.com/track/xyz")
    assert resolved == {"tidal_id": "123456", "qobuz_id": "987654", "isrc": "USRC17607839"}


def test_resolve_spotify_to_tidal_returns_none_without_tidal(monkeypatch) -> None:
    payload = {
        "entitiesByUniqueId": {
            "SPOTIFY_SONG::abc": {"isrc": "USRC17607839"},
            "QOBUZ_SONG::987654": {"id": "987654"},
        }
    }

    def fake_get(*_args, **_kwargs):
        return _response(200, payload)

    monkeypatch.setattr("tagslut.intake.songlink.httpx.get", fake_get)

    assert resolve_spotify_to_tidal("https://open.spotify.com/track/xyz") is None


def test_resolve_spotify_to_tidal_http_429_returns_none(monkeypatch) -> None:
    def fake_get(*_args, **_kwargs):
        return _response(429)

    monkeypatch.setattr("tagslut.intake.songlink.httpx.get", fake_get)

    assert resolve_spotify_to_tidal("https://open.spotify.com/track/xyz") is None

