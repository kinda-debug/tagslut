from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tagslut.exec.transcoder import FFmpegNotFoundError, TranscodeError, transcode_to_mp3


def test_raises_if_ffmpeg_not_found(tmp_path: Path):
    src = tmp_path / "track.flac"
    src.write_bytes(b"fake")
    with patch("tagslut.exec.transcoder.shutil.which", return_value=None):
        with pytest.raises(FFmpegNotFoundError):
            transcode_to_mp3(src, tmp_path / "out")


def test_raises_if_source_not_found(tmp_path: Path):
    with patch("tagslut.exec.transcoder.shutil.which", return_value="/usr/bin/ffmpeg"):
        with pytest.raises(FileNotFoundError):
            transcode_to_mp3(tmp_path / "nonexistent.flac", tmp_path / "out")


def test_raises_on_ffmpeg_error(tmp_path: Path):
    src = tmp_path / "track.flac"
    src.write_bytes(b"fake")
    mock_result = MagicMock(returncode=1, stderr="error")
    with patch("tagslut.exec.transcoder.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "tagslut.exec.transcoder.subprocess.run", return_value=mock_result
    ), patch("tagslut.exec.transcoder.FLAC", side_effect=Exception("no tags")), patch(
        "tagslut.exec.transcoder._apply_id3_tags"
    ):
        with pytest.raises(TranscodeError):
            transcode_to_mp3(src, tmp_path / "out")


def test_skips_existing_when_no_overwrite(tmp_path: Path):
    src = tmp_path / "track.flac"
    src.write_bytes(b"fake")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()
    existing = dest_dir / "track.mp3"
    existing.write_bytes(b"existing")

    with patch("tagslut.exec.transcoder.shutil.which", return_value="/usr/bin/ffmpeg"), patch(
        "tagslut.exec.transcoder.FLAC", side_effect=Exception()
    ), patch("tagslut.exec.transcoder.subprocess.run") as mock_run:
        result = transcode_to_mp3(src, dest_dir, overwrite=False)

    mock_run.assert_not_called()
    assert result == existing
