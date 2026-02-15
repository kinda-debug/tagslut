"""Module description placeholder."""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path

from tagslut import utils


def test_compute_md5(tmp_path: Path) -> None:
    target = tmp_path / "example.bin"
    target.write_bytes(b"hello world")
    expected = hashlib.md5(b"hello world").hexdigest()
    assert utils.compute_md5(target) == expected


def test_iter_audio_files_filters_extensions(tmp_path: Path) -> None:
    audio = tmp_path / "track.flac"
    audio.write_bytes(b"data")
    ignored = tmp_path / "notes.txt"
    ignored.write_text("text")
    found = list(utils.iter_audio_files(tmp_path))
    assert found == [audio]


def test_normalise_path_returns_nfc_absolute(tmp_path: Path) -> None:
    raw = tmp_path / "Cafe\u0301" / "song.flac"
    expected_dir = raw.parent
    normalised = utils.normalise_path(str(raw))
    assert unicodedata.is_normalized("NFC", normalised)
    assert normalised.endswith("song.flac")
    assert normalised.startswith(utils.normalise_path(expected_dir.as_posix()))
