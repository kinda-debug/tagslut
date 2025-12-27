from __future__ import annotations

from pathlib import Path

import pytest

from dedupe.utils.config import get_config


def test_get_config_reads_env_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[libraries]\ndotad_final = '/final'\n")

    monkeypatch.setenv("DEDUPE_CONFIG", str(config_path))
    data = get_config()

    assert data["libraries"]["dotad_final"] == "/final"
