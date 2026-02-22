from __future__ import annotations

from pathlib import Path
import shutil

from tagslut.dj import key_detection


def test_is_keyfinder_available_false(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert key_detection.is_keyfinder_available() is False


def test_detect_key_graceful_fallback_when_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    path = tmp_path / "audio.flac"
    path.write_bytes(b"test")
    assert key_detection.detect_key(path) is None
