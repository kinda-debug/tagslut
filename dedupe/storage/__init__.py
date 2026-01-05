"""Storage layer for dedupe.

Keep package import lightweight and avoid importing optional schema helpers.
"""

from __future__ import annotations

import importlib
from typing import Any

from .models import AudioFile

__all__ = [
    "AudioFile",
    "models",
    "schema",
    "queries",
    "LIBRARY_TABLE",
    "PICARD_MOVES_TABLE",
    "initialise_library_schema",
    "initialise_step0_schema",
]


def __getattr__(name: str) -> Any:
    if name in {"models", "schema", "queries"}:
        return importlib.import_module(f"{__name__}.{name}")
    if name in {
        "LIBRARY_TABLE",
        "PICARD_MOVES_TABLE",
        "initialise_library_schema",
        "initialise_step0_schema",
    }:
        schema = importlib.import_module(f"{__name__}.schema")
        return getattr(schema, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
