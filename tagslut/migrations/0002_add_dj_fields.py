"""Compatibility shim for legacy imports.

Canonical migration implementation lives in:
tagslut/storage/migrations/0002_add_dj_fields.py
"""

from __future__ import annotations

import importlib
import sqlite3

_mod = importlib.import_module("tagslut.storage.migrations.0002_add_dj_fields")
MIGRATION_ID = _mod.MIGRATION_ID


def up(conn: sqlite3.Connection) -> None:
    _mod.up(conn)


def down(conn: sqlite3.Connection) -> None:
    _mod.down(conn)
