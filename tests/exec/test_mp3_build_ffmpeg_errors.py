"""Test MP3 output validation after FFmpeg transcoding."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tagslut.exec.transcoder import (
    TranscodeError,
    _run_ffmpeg_transcode,
    _validate_mp3_output,
)
from tagslut.exec.transcoder import FFmpegNotFoundError, transcode_to_mp3
from tagslut.exec.dj_pool_wizard import execute_plan


def test_ffmpeg_missing_raises_ffmpeg_not_found_error(tmp_path: Path):
    """transcode_to_mp3 should raise FFmpegNotFoundError when ffmpeg is missing."""
    src = tmp_path / "track.flac"
    src.write_bytes(b"fake")
    dest_dir = tmp_path / "out"
    dest_dir.mkdir()

    with patch("tagslut.exec.transcoder.shutil.which", return_value=None):
        with pytest.raises(FFmpegNotFoundError):
            transcode_to_mp3(src, dest_dir)


def test_ffmpeg_nonzero_exit_raises_transcode_error(tmp_path: Path):
    """_run_ffmpeg_transcode should raise TranscodeError on ffmpeg non-zero exit."""
    src = tmp_path / "track.flac"
    src.write_bytes(b"fake")
    dest = tmp_path / "output.mp3"

    mock_result = MagicMock(returncode=1, stderr="codec error")
    with patch("tagslut.exec.transcoder.subprocess.run", return_value=mock_result):
        with pytest.raises(TranscodeError, match="ffmpeg failed"):
            _run_ffmpeg_transcode(src, dest, bitrate=320, ffmpeg_path="ffmpeg", validate_output=False)


def test_output_file_missing_raises_transcode_error(tmp_path: Path):
    """_validate_mp3_output should raise TranscodeError when file is missing."""
    dest = tmp_path / "output.mp3"

    with pytest.raises(TranscodeError, match="transcode output missing"):
        _validate_mp3_output(dest)


def test_output_file_too_small_raises_transcode_error(tmp_path: Path):
    """_validate_mp3_output should raise TranscodeError when file is < 4KB."""
    dest = tmp_path / "output.mp3"
    dest.write_bytes(b"\x00" * 100)  # 100-byte file

    with pytest.raises(TranscodeError, match="suspiciously small"):
        _validate_mp3_output(dest)


def test_output_file_unreadable_by_mutagen_raises_transcode_error(tmp_path: Path):
    """_validate_mp3_output should raise TranscodeError when mutagen can't parse file."""
    dest = tmp_path / "output.mp3"
    dest.write_bytes(b"\x00" * 4096)  # 4KB of zeros (invalid MP3)

    with patch("mutagen.mp3.MP3", side_effect=Exception("not an MP3")):
        with pytest.raises(TranscodeError, match="unreadable by mutagen"):
            _validate_mp3_output(dest)


def test_valid_output_does_not_raise(tmp_path: Path):
    """_validate_mp3_output should not raise when file is valid."""
    dest = tmp_path / "output.mp3"
    dest.write_bytes(b"\x00" * 4096)  # Meets size requirement

    mock_audio = MagicMock()
    mock_audio.info.length = 210.0

    with patch("mutagen.mp3.MP3", return_value=mock_audio):
        # Should not raise
        _validate_mp3_output(dest)


def test_transcode_error_surfaces_in_pool_wizard_failures(tmp_path: Path):
    """TranscodeError from validation should appear in execute_plan failures list."""
    # Minimal in-memory scenario
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = OFF")

    # Create minimal schema
    conn.execute(
        """
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            dj_pool_path TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE track_identities (
            identity_id INTEGER PRIMARY KEY,
            v3_source_id TEXT
        )
        """
    )

    # Patch transcode_to_mp3_from_snapshot to raise TranscodeError
    with patch("tagslut.exec.dj_pool_wizard.transcode_to_mp3_from_snapshot",
               side_effect=TranscodeError("test validation failure")):
        with patch("tagslut.exec.dj_pool_wizard.resolve_dj_tag_snapshot") as mock_resolve:
            mock_resolve.return_value = MagicMock(
                bpm=120, musical_key="A", energy_1_10=7
            )

            plan_rows = [
                {
                    "selected": True,
                    "cache_action": "transcode",
                    "identity_id": 1,
                    "master_path": "/fake/master.flac",
                    "final_dest_path": "/fake/output.mp3",
                }
            ]
            profile = {"bitrate": 320}
            run_dir = tmp_path

            receipts, failures = execute_plan(conn, plan_rows, profile, run_dir)

            # Should have one failure with transcode_failed error type
            assert len(failures) == 1
            assert failures[0]["error_type"] == "transcode_failed"
            assert "test validation failure" in failures[0]["error_message"]
