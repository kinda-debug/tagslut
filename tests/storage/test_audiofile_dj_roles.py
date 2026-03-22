from __future__ import annotations

from pathlib import Path

import pytest

from tagslut.storage.models import AudioFile


def _audio_file(**kwargs: object) -> AudioFile:
    return AudioFile(
        path=Path("/music/test.flac"),
        checksum="abc123",
        duration=1.0,
        bit_depth=16,
        sample_rate=44100,
        bitrate=900,
        metadata={},
        **kwargs,
    )


def test_audiofile_accepts_valid_dj_set_role() -> None:
    audio = _audio_file(dj_set_role="groove")

    assert audio.dj_set_role == "groove"


def test_audiofile_rejects_invalid_dj_set_role() -> None:
    with pytest.raises(ValueError, match="Invalid dj_set_role"):
        _audio_file(dj_set_role="emergency")


def test_audiofile_accepts_valid_dj_subrole() -> None:
    audio = _audio_file(dj_subrole="closer")

    assert audio.dj_subrole == "closer"


def test_audiofile_rejects_invalid_dj_subrole() -> None:
    with pytest.raises(ValueError, match="Invalid dj_subrole"):
        _audio_file(dj_subrole="bad_value")


def test_audiofile_allows_missing_dj_roles() -> None:
    audio = _audio_file(dj_set_role=None, dj_subrole=None)

    assert audio.dj_set_role is None
    assert audio.dj_subrole is None
