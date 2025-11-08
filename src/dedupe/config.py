"""Helpers for loading directory paths from ``config.toml``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "DEFAULT_GARBAGE_ROOT",
    "DEFAULT_LIBRARY_ROOT",
    "DEFAULT_QUARANTINE_ROOT",
    "PathConfig",
    "load_path_config",
]

DEFAULT_LIBRARY_ROOT = Path("/Volumes/dotad/MUSIC")
# Default location of the primary music library.

DEFAULT_QUARANTINE_ROOT = Path("/Volumes/dotad/Quarantine")
# Default location for reviewed quarantine files.

DEFAULT_GARBAGE_ROOT = Path("/Volumes/dotad/Garbage")
# Default location for archived duplicate candidates.

_KEY_TEMPLATE = r"^\s*{key}\s*=\s*\"([^\"]+)\""


@dataclass(frozen=True)
class PathConfig:
    """Filesystem locations for the library and auxiliary directories."""

    library_root: Path
    quarantine_root: Path
    garbage_root: Path


def _extract_path(text: str, key: str, default: Path) -> Path:
    """Return the configured path for *key* or *default* when missing."""

    pattern = re.compile(_KEY_TEMPLATE.format(key=re.escape(key)), re.MULTILINE)
    match = pattern.search(text)
    if match:
        return Path(match.group(1))
    return default


def load_path_config(config_path: Path) -> PathConfig:
    """Load the path configuration from ``config.toml``.

    The loader keeps the defaults when the file is absent or omits one of the
    expected keys, ensuring commands always fall back to sensible directories.
    """

    try:
        text = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    except OSError:
        text = ""

    return PathConfig(
        library_root=_extract_path(text, "root", DEFAULT_LIBRARY_ROOT),
        quarantine_root=_extract_path(
            text,
            "quarantine",
            DEFAULT_QUARANTINE_ROOT,
        ),
        garbage_root=_extract_path(text, "garbage", DEFAULT_GARBAGE_ROOT),
    )
