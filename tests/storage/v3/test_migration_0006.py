from __future__ import annotations

import importlib
import sqlite3

from tagslut.storage.v3.schema import V3_SCHEMA_VERSION_TRACK_IDENTITY_PHASE1


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _index_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    return {str(row[0]) for row in rows}


def _create_schema_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE schema_migrations (
            id INTEGER PRIMARY KEY,
            schema_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
            note TEXT,
            UNIQUE(schema_name, version)
        )
        """
    )


def _create_pre_0006_track_identity(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE track_identity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identity_key TEXT NOT NULL UNIQUE,
            isrc TEXT,
            beatport_id TEXT,
            artist_norm TEXT,
            title_norm TEXT
        )
        """
    )


def test_migration_0006_adds_phase1_columns_indexes_and_version_record() -> None:
    module = importlib.import_module("tagslut.storage.v3.migrations.0006_track_identity_phase1")
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        _create_pre_0006_track_identity(conn)

        module.up(conn)

        columns = _column_names(conn, "track_identity")
        indexes = _index_names(conn)
        row = conn.execute(
            "SELECT note FROM schema_migrations WHERE schema_name='v3' AND version = ?",
            (module.VERSION,),
        ).fetchone()
    finally:
        conn.close()

    assert module.VERSION == V3_SCHEMA_VERSION_TRACK_IDENTITY_PHASE1 == 6
    assert {
        "canonical_title",
        "canonical_artist",
        "canonical_album",
        "canonical_bpm",
        "canonical_key",
        "canonical_genre",
        "canonical_sub_genre",
        "canonical_year",
        "canonical_release_date",
        "canonical_label",
        "canonical_catalog_number",
        "canonical_duration",
        "tidal_id",
        "qobuz_id",
        "deezer_id",
        "traxsource_id",
        "musicbrainz_id",
        "itunes_id",
        "merged_into_id",
    }.issubset(columns)
    assert {
        "idx_track_identity_isrc_not_null",
        "idx_track_identity_beatport_not_null",
        "idx_track_identity_tidal_not_null",
        "idx_track_identity_qobuz_not_null",
        "idx_track_identity_musicbrainz_not_null",
        "idx_track_identity_merged_into_not_null",
        "idx_track_identity_artist_title_norm",
    }.issubset(indexes)
    assert row is not None
    assert row[0] == "phase 1 canonical identity extension"


def test_migration_0006_is_idempotent_and_keeps_merged_into_nullable() -> None:
    module = importlib.import_module("tagslut.storage.v3.migrations.0006_track_identity_phase1")
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        _create_pre_0006_track_identity(conn)

        module.up(conn)
        module.up(conn)
        conn.execute(
            """
            INSERT INTO track_identity (
                identity_key,
                artist_norm,
                title_norm,
                merged_into_id
            ) VALUES (?, ?, ?, ?)
            """,
            ("id:root", "artist", "title", None),
        )
        row = conn.execute(
            "SELECT merged_into_id FROM track_identity WHERE identity_key = ?",
            ("id:root",),
        ).fetchone()
        notnull = {
            str(info[1]): int(info[3])
            for info in conn.execute("PRAGMA table_info(track_identity)").fetchall()
        }
        version_rows = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE schema_name='v3' AND version = ?",
            (module.VERSION,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] is None
    assert notnull["merged_into_id"] == 0
    assert version_rows is not None
    assert int(version_rows[0]) == 1
