"""Migration 0007: rename early phase-1 upgrade columns to canonical names.

Rollback is restore-from-backup only.
"""

from __future__ import annotations

import sqlite3

VERSION = 7


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _rename_column_if_needed(
    conn: sqlite3.Connection,
    table: str,
    old_name: str,
    new_name: str,
) -> None:
    if _column_exists(conn, table, new_name):
        return
    if not _column_exists(conn, table, old_name):
        return
    conn.execute(f"ALTER TABLE {table} RENAME COLUMN {old_name} TO {new_name}")


def up(conn: sqlite3.Connection) -> None:
    import sqlite3 as _sqlite3

    if tuple(int(x) for x in _sqlite3.sqlite_version.split(".")) < (3, 25, 0):
        raise RuntimeError(
            f"RENAME COLUMN requires SQLite >= 3.25.0; found {_sqlite3.sqlite_version}. "
            "Upgrade SQLite before running this migration."
        )

    _rename_column_if_needed(conn, "track_identity", "label", "canonical_label")
    _rename_column_if_needed(conn, "track_identity", "catalog_number", "canonical_catalog_number")
    _rename_column_if_needed(conn, "track_identity", "canonical_duration_s", "canonical_duration")

    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES ('v3', ?, ?)
        """,
        (VERSION, "rename phase 1 track identity columns to canonical names"),
    )
