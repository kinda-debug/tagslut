"""Migration 0020: add structured identity resolver artifacts."""

from __future__ import annotations

import sqlite3

from tagslut.storage.v3.schema import (
    V3_SCHEMA_VERSION_IDENTITY_RESOLUTION_ARTIFACTS,
    ensure_identity_resolution_artifacts,
)

VERSION = V3_SCHEMA_VERSION_IDENTITY_RESOLUTION_ARTIFACTS


def up(conn: sqlite3.Connection) -> None:
    ensure_identity_resolution_artifacts(conn)
