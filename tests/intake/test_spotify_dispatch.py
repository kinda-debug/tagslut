from __future__ import annotations

import pytest

from tagslut.intake.dispatch import IntakeError, dispatch_intake_url


def test_dispatch_spotify_track_resolves_to_tidal(monkeypatch) -> None:
    monkeypatch.setattr(
        "tagslut.intake.dispatch.resolve_spotify_to_tidal",
        lambda _url: {"tidal_id": "424242"},
    )

    dispatch = dispatch_intake_url("https://open.spotify.com/track/abc123")
    assert dispatch.url == "https://tidal.com/track/424242"
    assert dispatch.spotify_url == "https://open.spotify.com/track/abc123"


def test_dispatch_spotify_track_missing_tidal_raises(monkeypatch) -> None:
    monkeypatch.setattr("tagslut.intake.dispatch.resolve_spotify_to_tidal", lambda _url: None)

    with pytest.raises(IntakeError) as exc:
        dispatch_intake_url("https://open.spotify.com/track/abc123")
    assert "song.link could not resolve" in str(exc.value)


def test_dispatch_spotify_playlist_raises_immediately(monkeypatch) -> None:
    def should_not_be_called(_url: str):
        raise AssertionError("resolver should not be called for playlist URLs")

    monkeypatch.setattr("tagslut.intake.dispatch.resolve_spotify_to_tidal", should_not_be_called)

    with pytest.raises(IntakeError):
        dispatch_intake_url("https://open.spotify.com/playlist/37i9dQZF1DX4JAvHpjipBk")

