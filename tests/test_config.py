from __future__ import annotations

from pathlib import Path

import pytest

from tagslut.utils.config import get_config


def test_get_config_reads_env_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[library]\nname = 'COMMUNE'\nroot = '/Volumes/COMMUNE'\n")

    monkeypatch.setenv("TAGSLUT_CONFIG", str(config_path))
    data = get_config()

    assert data["library"]["root"] == "/Volumes/COMMUNE"
