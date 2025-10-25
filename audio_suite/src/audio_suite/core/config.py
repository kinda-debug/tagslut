"""Configuration loader for Audio Suite.

This module uses Dynaconf to assemble configuration values from multiple
sources in a predictable order:

1. Built‑in defaults defined in :file:`settings.toml` shipped with the
   package.
2. User settings stored in ``~/.config/audio_suite/settings.toml`` (optional).
3. Environment variables prefixed with ``AUDIO_SUITE_``.
4. Secrets loaded from ``.secrets.toml`` in the project root (ignored by git).

Consumers should call :func:`get_settings` to obtain a Dynaconf instance.  Do
not import the ``settings`` object directly from Dynaconf; doing so will
result in global state that is difficult to test.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dynaconf import Dynaconf


_SETTINGS_CACHE: Optional[Dynaconf] = None


def get_settings() -> Dynaconf:
    """Return a Dynaconf settings object with cached values.

    The settings are loaded lazily on first call and cached for the
    duration of the process.  Subsequent calls return the same object.
    """
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is not None:
        return _SETTINGS_CACHE

    # Base directory is the project root (one level above this file's parent)
    base_dir = Path(__file__).resolve().parents[2]
    default_settings_file = base_dir / "settings.toml"

    # User config file under ~/.config/audio_suite/settings.toml
    user_config_file = Path.home() / ".config" / "audio_suite" / "settings.toml"

    # Optional secrets file in project root (.secrets.toml) – not shipped in source
    secrets_file = base_dir / ".secrets.toml"

    _SETTINGS_CACHE = Dynaconf(
        envvar_prefix="AUDIO_SUITE",
        settings_files=[str(default_settings_file), str(user_config_file)],
        secrets=str(secrets_file) if secrets_file.exists() else None,
        environments=True,
        load_dotenv=False,
    )
    return _SETTINGS_CACHE


def save_user_settings(data: dict) -> None:
    """Persist user settings to the per‑user configuration file.

    The file is created if it does not exist.  Only keys present in
    ``data`` are written; existing values are preserved.
    """
    user_file = Path.home() / ".config" / "audio_suite" / "settings.toml"
    user_file.parent.mkdir(parents=True, exist_ok=True)
    # Read existing values
    existing = {}
    if user_file.exists():
        existing = Dynaconf(settings_files=[str(user_file)]).as_dict()
    existing.update(data)
    # Write back as TOML
    toml_lines = ["[default]\n"]
    for key, value in existing.items():
        toml_lines.append(f"{key} = {repr(value)}\n")
    user_file.write_text("".join(toml_lines), encoding="utf-8")