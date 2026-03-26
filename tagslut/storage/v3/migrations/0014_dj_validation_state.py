"""Migration 0014: add DJ validation audit state."""

from __future__ import annotations

import sqlite3

SCHEMA_NAME = "v3"
VERSION = 14


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dj_validation_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state_hash TEXT NOT NULL,
            passed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (SCHEMA_NAME, VERSION, "0014_dj_validation_state.py"),
    )
    conn.commit()
