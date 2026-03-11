"""Migration 0007: add partial UNIQUE index on track_identity.isrc (v3).

Prevents duplicate non-empty ISRC values from being stored in the v3
track_identity table. The index is partial so that rows with NULL or
blank ISRC are not affected.

This closes the data-integrity gap where _matched_identity_id_by_field
resolves by ISRC tier but two identity rows could share the same ISRC,
causing the resolver to silently pick whichever row has the lowest id.
"""

from __future__ import annotations

import sqlite3

INDEX_NAME = "idx_track_identity_isrc_unique"
TABLE_NAME = "track_identity"


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
    if not _table_exists(conn, TABLE_NAME):
        return
    if not _has_column(conn, TABLE_NAME, "isrc"):
        return

    conn.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
        ON {TABLE_NAME}(isrc)
        WHERE isrc IS NOT NULL AND TRIM(isrc) != ''
        """
    )


def down(conn: sqlite3.Connection) -> None:
    conn.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
