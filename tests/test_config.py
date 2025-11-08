"""Tests for loading directory settings from ``config.toml``."""

from __future__ import annotations

from pathlib import Path

from dedupe.config import (
    DEFAULT_GARBAGE_ROOT,
    DEFAULT_LIBRARY_ROOT,
    DEFAULT_QUARANTINE_ROOT,
    load_path_config,
)


def test_load_path_config_defaults(tmp_path: Path) -> None:
    """Falling back to defaults should work when config.toml is missing."""

    config_path = tmp_path / "config.toml"
    config = load_path_config(config_path)

    assert config.library_root == DEFAULT_LIBRARY_ROOT
    assert config.quarantine_root == DEFAULT_QUARANTINE_ROOT
    assert config.garbage_root == DEFAULT_GARBAGE_ROOT


def test_load_path_config_custom_values(tmp_path: Path) -> None:
    """Custom directory overrides should be returned from the loader."""

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[paths]
root = "/music"
quarantine = "/quarantine"
garbage = "/garbage"
        """.strip()
    )

    config = load_path_config(config_path)

    assert config.library_root == Path("/music")
    assert config.quarantine_root == Path("/quarantine")
    assert config.garbage_root == Path("/garbage")
