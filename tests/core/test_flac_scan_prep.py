from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tagslut.core.flac_scan_prep import _convert_to_flac


def test_convert_to_flac_returns_verify_failure_without_name_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.wav"
    dest = tmp_path / "output.flac"
    source.write_bytes(b"wav")
    dest.write_bytes(b"bad flac")

    monkeypatch.setattr("tagslut.core.flac_scan_prep.shutil.which", lambda name: "/usr/bin/tool")

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        if cmd[0] == "ffmpeg":
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        if cmd[0] == "flac":
            return SimpleNamespace(returncode=1, stderr="verify failed", stdout="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("tagslut.core.flac_scan_prep.subprocess.run", fake_run)

    converted, error = _convert_to_flac(source, dest)

    assert converted is False
    assert error == "verify failed"
    assert not dest.exists()
