"""Database schema helpers for the unified dedupe library."""

from __future__ import annotations

from dedupe.storage.schema import (
    LIBRARY_TABLE,
    initialise_library_schema,
)

__all__ = ["LIBRARY_TABLE", "initialise_library_schema"]
