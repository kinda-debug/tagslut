"""Database schema helpers for the unified dedupe library."""

from __future__ import annotations

import sqlite3

LIBRARY_TABLE = "library_files"
PICARD_MOVES_TABLE = "picard_moves"
DEFAULT_LIBRARY_STATE = "FINAL"


def _ensure_columns(
    connection: sqlite3.Connection,
    table: str,
    columns: dict[str, str],
) -> None:
    """Ensure *columns* exist on *table*, adding them if needed."""

    existing = {
        row[1] for row in connection.execute(f"PRAGMA table_info({table});").fetchall()
    }
    for column, definition in columns.items():
        if column in existing:
            continue
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialise_library_schema(connection: sqlite3.Connection) -> None:
    """Ensure the core library table exists in the provided connection."""

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LIBRARY_TABLE} (
            path TEXT PRIMARY KEY,
            size_bytes INTEGER,
            mtime REAL,
            checksum TEXT,
            duration REAL,
            sample_rate INTEGER,
            bit_rate INTEGER,
            channels INTEGER,
            bit_depth INTEGER,
            tags_json TEXT,
            fingerprint TEXT,
            fingerprint_duration REAL,
            dup_group TEXT,
            duplicate_rank INTEGER,
            is_canonical INTEGER,
            extra_json TEXT,
            library_state TEXT DEFAULT '{DEFAULT_LIBRARY_STATE}',
            flac_ok INTEGER
        )
        """
    )

    _ensure_columns(
        connection,
        LIBRARY_TABLE,
        {
            "extra_json": "TEXT",
            "library_state": f"TEXT DEFAULT '{DEFAULT_LIBRARY_STATE}'",
            "flac_ok": "INTEGER",
        },
    )

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {PICARD_MOVES_TABLE} (
            old_path TEXT NOT NULL,
            new_path TEXT NOT NULL,
            checksum TEXT,
            moved_at REAL
        )
        """
    )
