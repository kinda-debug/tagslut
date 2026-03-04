from unittest.mock import MagicMock, patch

import pytest

from tagslut.scan.validate import decode_probe_edges, probe_duration_ffprobe


def test_probe_duration_returns_none_when_ffprobe_missing(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    with patch("shutil.which", return_value=None):
        assert probe_duration_ffprobe(f) is None


def test_probe_duration_returns_float(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    mock = MagicMock(returncode=0, stdout="245.3\n", stderr="")
    with patch("shutil.which", return_value="/usr/bin/ffprobe"), patch(
        "subprocess.run", return_value=mock
    ):
        result = probe_duration_ffprobe(f)
    assert result == pytest.approx(245.3)


def test_probe_duration_returns_none_on_error(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    mock = MagicMock(returncode=1, stdout="", stderr="error")
    with patch("shutil.which", return_value="/usr/bin/ffprobe"), patch(
        "subprocess.run", return_value=mock
    ):
        assert probe_duration_ffprobe(f) is None


def test_decode_probe_returns_empty_when_ffmpeg_missing(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    with patch("shutil.which", return_value=None):
        assert decode_probe_edges(f) == []


def test_decode_probe_returns_errors(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    mock_ok = MagicMock(returncode=0, stderr="")
    mock_err = MagicMock(returncode=0, stderr="Invalid data found")
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "subprocess.run", side_effect=[mock_err, mock_ok]
    ):
        errors = decode_probe_edges(f, duration=300.0)
    assert len(errors) >= 1
    assert "Invalid data found" in errors[0]


def test_decode_probe_empty_on_clean_file(tmp_path):
    f = tmp_path / "track.flac"
    f.write_bytes(b"fake")
    mock_clean = MagicMock(returncode=0, stderr="")
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "subprocess.run", return_value=mock_clean
    ):
        assert decode_probe_edges(f, duration=300.0) == []
