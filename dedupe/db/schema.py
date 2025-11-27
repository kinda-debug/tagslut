"""Database schema helpers for the unified dedupe library."""

from __future__ import annotations

import sqlite3

LIBRARY_TABLE = "library_files"


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
            extra_json TEXT
        )
        """
    )
