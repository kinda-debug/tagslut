"""Configuration loader for dedupe."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - fallback for older Python
    import tomli as tomllib  # type: ignore


DEFAULT_CONFIG_NAME = "config.toml"


def get_config(path: Path | None = None) -> dict[str, Any]:
    """Return the parsed configuration from *path* or the default config."""

    config_path = path
    if config_path is None:
        env_path = os.environ.get("DEDUPE_CONFIG")
        if env_path:
            config_path = Path(env_path)
        else:
            config_path = Path(DEFAULT_CONFIG_NAME)

    config_path = config_path.expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("rb") as handle:
        return tomllib.load(handle)
