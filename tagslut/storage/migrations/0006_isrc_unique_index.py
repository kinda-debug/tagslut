"""Migration 0006: add partial UNIQUE index for files.isrc."""

from __future__ import annotations

import sqlite3


INDEX_NAME = "idx_files_isrc"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row and int(row[0]) > 0)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def up(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "files"):
        return
    if not _has_column(conn, "files", "isrc"):
        return

    conn.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
        ON files(isrc)
        WHERE isrc IS NOT NULL AND TRIM(isrc) != ''
        """
    )


def down(conn: sqlite3.Connection) -> None:
    conn.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
