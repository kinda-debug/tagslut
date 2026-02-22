"""Unified toolkit for scanning, matching, and recovering audio libraries.

Keep package import lightweight: submodules are loaded lazily.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "decide",
    "core",
    "policy",
    "storage",
    "utils",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
