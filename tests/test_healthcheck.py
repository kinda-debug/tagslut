"""Tests for the FLAC health scoring utilities."""

from __future__ import annotations

from pathlib import Path

import dedupe.healthcheck as healthcheck


def _build_fake_flac(tags: dict[str, str], duration: float = 120.0, md5: str | None = "abc"):
    class _Info:
        length = duration
        md5_signature = md5

    class _Audio:
        info = _Info()

        def __init__(self, _: Path) -> None:
            self.tags = tags

    return _Audio


def test_evaluate_flac_success(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "ok.flac"
    target.write_bytes(b"fake-flac")

    fake_tags = {
        "Artist": "Example",
        "Album": "Album",
        "Title": "Track",
        "Date": "2024",
        "TrackNumber": "1",
    }
    monkeypatch.setattr(healthcheck, "FLAC", _build_fake_flac(fake_tags))
    monkeypatch.setattr(healthcheck, "_run_flac_test", lambda _: True)

    result = healthcheck.evaluate_flac(target)

    assert result.score == 10
    assert result.audio_ok is True
    assert result.tags_ok is True
    assert result.reasons == []


def test_evaluate_flac_missing_tags(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "missing_tags.flac"
    target.write_bytes(b"fake-flac")

    fake_tags = {
        "Artist": "Example",
        "Title": "Track",
    }
    monkeypatch.setattr(healthcheck, "FLAC", _build_fake_flac(fake_tags))
    monkeypatch.setattr(healthcheck, "_run_flac_test", lambda _: True)

    result = healthcheck.evaluate_flac(target)

    assert result.score == 8  # missing required tags reduces score
    assert result.tags_ok is False
    assert any("Missing required tags" in reason for reason in result.reasons)


def test_evaluate_flac_without_mutagen(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "no_mutagen.flac"
    target.write_bytes(b"fake-flac")

    monkeypatch.setattr(healthcheck, "FLAC", None)
    monkeypatch.setattr(healthcheck, "_run_flac_test", lambda _: True)

    result = healthcheck.evaluate_flac(target)

    assert result.audio_ok is True
    assert result.tags_ok is False
    assert result.score == 6  # audio valid but tags unavailable
    assert "mutagen is not available" in " ".join(result.reasons)
