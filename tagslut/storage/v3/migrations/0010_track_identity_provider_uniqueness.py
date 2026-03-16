"""Migration 0010: enforce active provider-id uniqueness for v3 identities."""

from __future__ import annotations

import sqlite3

VERSION = 10

PROVIDER_COLUMNS: tuple[str, ...] = (
    "beatport_id",
    "tidal_id",
    "qobuz_id",
    "spotify_id",
)

ACTIVE_PROVIDER_DUPLICATE_AUDIT_SQL = """
WITH duplicate_groups AS (
    SELECT 'beatport_id' AS provider_column, beatport_id AS provider_id, COUNT(*) AS row_count
    FROM track_identity
    WHERE beatport_id IS NOT NULL
      AND TRIM(beatport_id) != ''
      AND merged_into_id IS NULL
    GROUP BY beatport_id
    HAVING COUNT(*) > 1
    UNION ALL
    SELECT 'tidal_id' AS provider_column, tidal_id AS provider_id, COUNT(*) AS row_count
    FROM track_identity
    WHERE tidal_id IS NOT NULL
      AND TRIM(tidal_id) != ''
      AND merged_into_id IS NULL
    GROUP BY tidal_id
    HAVING COUNT(*) > 1
    UNION ALL
    SELECT 'qobuz_id' AS provider_column, qobuz_id AS provider_id, COUNT(*) AS row_count
    FROM track_identity
    WHERE qobuz_id IS NOT NULL
      AND TRIM(qobuz_id) != ''
      AND merged_into_id IS NULL
    GROUP BY qobuz_id
    HAVING COUNT(*) > 1
    UNION ALL
    SELECT 'spotify_id' AS provider_column, spotify_id AS provider_id, COUNT(*) AS row_count
    FROM track_identity
    WHERE spotify_id IS NOT NULL
      AND TRIM(spotify_id) != ''
      AND merged_into_id IS NULL
    GROUP BY spotify_id
    HAVING COUNT(*) > 1
)
SELECT provider_column, provider_id, row_count
FROM duplicate_groups
ORDER BY provider_column ASC, provider_id ASC
"""


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _normalize_provider_values(conn: sqlite3.Connection, column: str) -> None:
    conn.execute(
        f"""
        UPDATE track_identity
        SET {column} = NULL
        WHERE {column} IS NOT NULL
          AND TRIM({column}) = ''
        """
    )
    conn.execute(
        f"""
        UPDATE track_identity
        SET {column} = TRIM({column})
        WHERE {column} IS NOT NULL
          AND {column} != TRIM({column})
        """
    )


def list_duplicate_active_provider_ids(
    conn: sqlite3.Connection,
) -> list[tuple[str, str, int]]:
    rows = conn.execute(ACTIVE_PROVIDER_DUPLICATE_AUDIT_SQL).fetchall()
    return [
        (str(row[0]), str(row[1]), int(row[2]))
        for row in rows
    ]


def up(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")

    required_columns = (*PROVIDER_COLUMNS, "merged_into_id")
    missing = [
        column for column in required_columns if not _column_exists(conn, "track_identity", column)
    ]
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise RuntimeError(f"track_identity missing required columns for migration 0010: {missing_text}")

    for column in PROVIDER_COLUMNS:
        _normalize_provider_values(conn, column)

    duplicates = list_duplicate_active_provider_ids(conn)
    if duplicates:
        details = ", ".join(
            f"{column}={value} count={count}" for column, value, count in duplicates
        )
        raise RuntimeError(f"duplicate active provider ids block migration 0010: {details}")

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_beatport_id
        ON track_identity(beatport_id)
        WHERE beatport_id IS NOT NULL
          AND TRIM(beatport_id) != ''
          AND merged_into_id IS NULL
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_tidal_id
        ON track_identity(tidal_id)
        WHERE tidal_id IS NOT NULL
          AND TRIM(tidal_id) != ''
          AND merged_into_id IS NULL
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_qobuz_id
        ON track_identity(qobuz_id)
        WHERE qobuz_id IS NOT NULL
          AND TRIM(qobuz_id) != ''
          AND merged_into_id IS NULL
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_spotify_id
        ON track_identity(spotify_id)
        WHERE spotify_id IS NOT NULL
          AND TRIM(spotify_id) != ''
          AND merged_into_id IS NULL
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES ('v3', ?, ?)
        """,
        (VERSION, "active provider-id unique partial indexes"),
    )
