"""Migration 0015: add issue_count and summary to dj_validation_state."""

from __future__ import annotations

import sqlite3

SCHEMA_NAME = "v3"
VERSION = 15


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        "ALTER TABLE dj_validation_state ADD COLUMN issue_count INTEGER NOT NULL DEFAULT 0"
    )
    conn.execute(
        "ALTER TABLE dj_validation_state ADD COLUMN summary TEXT"
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (SCHEMA_NAME, VERSION, "0015_dj_validation_state_audit.py"),
    )
    conn.commit()

