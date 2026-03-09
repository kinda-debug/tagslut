"""Migration 0006: canonical track_identity extension for upgrade-path DBs.

Rollback is restore-from-backup only.
"""

from __future__ import annotations

import sqlite3

VERSION = 6


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def up(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")

    additions = [
        ("canonical_title", "TEXT"),
        ("canonical_artist", "TEXT"),
        ("canonical_album", "TEXT"),
        ("canonical_bpm", "REAL"),
        ("canonical_key", "TEXT"),
        ("canonical_genre", "TEXT"),
        ("canonical_sub_genre", "TEXT"),
        ("canonical_year", "INTEGER"),
        ("canonical_release_date", "TEXT"),
        ("canonical_label", "TEXT"),
        ("canonical_catalog_number", "TEXT"),
        ("canonical_duration", "REAL"),
        ("tidal_id", "TEXT"),
        ("qobuz_id", "TEXT"),
        ("deezer_id", "TEXT"),
        ("traxsource_id", "TEXT"),
        ("musicbrainz_id", "TEXT"),
        ("itunes_id", "TEXT"),
    ]
    for column_name, column_type in additions:
        if not _column_exists(conn, "track_identity", column_name):
            conn.execute(f"ALTER TABLE track_identity ADD COLUMN {column_name} {column_type}")

    if not _column_exists(conn, "track_identity", "merged_into_id"):
        conn.execute(
            """
            ALTER TABLE track_identity
            ADD COLUMN merged_into_id INTEGER REFERENCES track_identity(id)
            """
        )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_track_identity_isrc_not_null
            ON track_identity(isrc)
            WHERE isrc IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_track_identity_beatport_not_null
            ON track_identity(beatport_id)
            WHERE beatport_id IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_track_identity_tidal_not_null
            ON track_identity(tidal_id)
            WHERE tidal_id IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_track_identity_qobuz_not_null
            ON track_identity(qobuz_id)
            WHERE qobuz_id IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_track_identity_musicbrainz_not_null
            ON track_identity(musicbrainz_id)
            WHERE musicbrainz_id IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_track_identity_merged_into_not_null
            ON track_identity(merged_into_id)
            WHERE merged_into_id IS NOT NULL
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_track_identity_artist_title_norm
            ON track_identity(artist_norm, title_norm)
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES ('v3', ?, ?)
        """,
        (VERSION, "phase 1 canonical identity extension"),
    )
