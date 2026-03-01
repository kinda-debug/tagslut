"""Compatibility shim for legacy imports.

Canonical migration implementation lives in:
tagslut/storage/migrations/0004_checksum_provenance.py
"""

from __future__ import annotations

import importlib
import sqlite3

_mod = importlib.import_module("tagslut.storage.migrations.0004_checksum_provenance")
ChecksumProvenanceMigration = _mod.ChecksumProvenanceMigration


def up(conn: sqlite3.Connection) -> None:
    _mod.up(conn)
