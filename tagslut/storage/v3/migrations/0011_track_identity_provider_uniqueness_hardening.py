"""Migration 0011: harden active provider-id uniqueness for additional v3 providers."""

from __future__ import annotations

import sqlite3

from tagslut.storage.v3.schema import (
    V3_SCHEMA_NAME,
    V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS_HARDENING,
)

VERSION = V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS_HARDENING

PROVIDER_COLUMNS: tuple[str, ...] = (
    "apple_music_id",
    "deezer_id",
    "traxsource_id",
)
WHITESPACE_CHARS = " \t\n\r"


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _normalize_provider_values(conn: sqlite3.Connection, column: str) -> None:
    conn.execute(
        f"""
        UPDATE track_identity
        SET {column} = NULL
        WHERE {column} IS NOT NULL
          AND TRIM({column}, '{WHITESPACE_CHARS}') = ''
        """
    )
    conn.execute(
        f"""
        UPDATE track_identity
        SET {column} = TRIM({column}, '{WHITESPACE_CHARS}')
        WHERE {column} IS NOT NULL
          AND {column} != TRIM({column}, '{WHITESPACE_CHARS}')
        """
    )


def list_duplicate_active_provider_ids(
    conn: sqlite3.Connection,
) -> list[tuple[str, str, int]]:
    duplicates: list[tuple[str, str, int]] = []
    for column in PROVIDER_COLUMNS:
        rows = conn.execute(
            f"""
            SELECT {column} AS provider_id, COUNT(*) AS row_count
            FROM track_identity
            WHERE {column} IS NOT NULL
              AND TRIM({column}, '{WHITESPACE_CHARS}') != ''
              AND merged_into_id IS NULL
            GROUP BY {column}
            HAVING COUNT(*) > 1
            ORDER BY {column} ASC
            """
        ).fetchall()
        duplicates.extend((column, str(row[0]), int(row[1])) for row in rows)
    return duplicates


def up(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")

    required_columns = (*PROVIDER_COLUMNS, "merged_into_id")
    missing = [
        column for column in required_columns if not _column_exists(conn, "track_identity", column)
    ]
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise RuntimeError(f"track_identity missing required columns for migration 0011: {missing_text}")

    for column in PROVIDER_COLUMNS:
        _normalize_provider_values(conn, column)

    duplicates = list_duplicate_active_provider_ids(conn)
    if duplicates:
        details = ", ".join(
            f"{column}={value} count={count}" for column, value, count in duplicates
        )
        raise RuntimeError(f"duplicate active provider ids block migration 0011: {details}")

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_apple_music_id
        ON track_identity(apple_music_id)
        WHERE apple_music_id IS NOT NULL
          AND TRIM(apple_music_id, ' \t\n\r') != ''
          AND merged_into_id IS NULL
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_deezer_id
        ON track_identity(deezer_id)
        WHERE deezer_id IS NOT NULL
          AND TRIM(deezer_id, ' \t\n\r') != ''
          AND merged_into_id IS NULL
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_traxsource_id
        ON track_identity(traxsource_id)
        WHERE traxsource_id IS NOT NULL
          AND TRIM(traxsource_id, ' \t\n\r') != ''
          AND merged_into_id IS NULL
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (
            V3_SCHEMA_NAME,
            V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS_HARDENING,
            "active provider-id unique partial indexes hardening pass",
        ),
    )
