from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tagslut.exec.transcoder import TranscodeError, _validate_mp3_output


def test_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "missing.mp3"

    with pytest.raises(TranscodeError, match="transcode output missing"):
        _validate_mp3_output(missing)


def test_file_too_small_raises(tmp_path: Path) -> None:
    path = tmp_path / "tiny.mp3"
    path.write_bytes(b"\x00" * 100)

    with pytest.raises(TranscodeError, match="suspiciously small"):
        _validate_mp3_output(path)


def test_garbage_bytes_raises(tmp_path: Path) -> None:
    path = tmp_path / "garbage.mp3"
    path.write_bytes(b"\x00" * 10_240)

    with patch("mutagen.mp3.MP3", side_effect=Exception("not an MP3")):
        with pytest.raises(TranscodeError, match="unreadable by mutagen"):
            _validate_mp3_output(path)


def test_valid_mock_mp3_passes(tmp_path: Path) -> None:
    path = tmp_path / "validish.mp3"
    path.write_bytes(b"\x00" * 8192)

    mock_audio = MagicMock()
    mock_audio.info.length = 210.0

    with patch("mutagen.mp3.MP3", return_value=mock_audio):
        _validate_mp3_output(path)


def test_duration_too_short_raises(tmp_path: Path) -> None:
    path = tmp_path / "short.mp3"
    path.write_bytes(b"\x00" * 8192)

    mock_audio = MagicMock()
    mock_audio.info.length = 0.1

    with patch("mutagen.mp3.MP3", return_value=mock_audio):
        with pytest.raises(TranscodeError, match="duration too short"):
            _validate_mp3_output(path)
