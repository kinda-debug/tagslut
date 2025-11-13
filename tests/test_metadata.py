from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from dedupe import metadata


@pytest.fixture(autouse=True)
def restore_ffprobe(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Ensure tests do not invoke the real ffprobe binary.
    monkeypatch.setattr(metadata, "which", lambda _: None)
    yield


def test_probe_audio_returns_basic_stats(tmp_path: Path) -> None:
    file_path = tmp_path / "audio.flac"
    file_path.write_bytes(b"flac data")
    info = metadata.probe_audio(file_path)
    assert info.path == file_path
    assert info.size_bytes == len(b"flac data")
    assert info.stream.duration is None
