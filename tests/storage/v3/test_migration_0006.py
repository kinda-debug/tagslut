from __future__ import annotations

import sqlite3
from pathlib import Path

from tagslut.storage.v3.migration_runner import run_pending_v3, verify_v3_migration
from tagslut.storage.v3.schema import (
    V3_SCHEMA_VERSION,
    V3_SCHEMA_VERSION_CANONICAL_IDENTITY,
    create_schema_v3,
)


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _index_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    return {str(row[0]) for row in rows}


def _create_v5_fixture(path: Path) -> Path:
    db_path = path / "music_v3.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE track_identity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_key TEXT NOT NULL UNIQUE,
                isrc TEXT,
                beatport_id TEXT,
                tidal_id TEXT,
                qobuz_id TEXT,
                spotify_id TEXT,
                apple_music_id TEXT,
                deezer_id TEXT,
                traxsource_id TEXT,
                itunes_id TEXT,
                musicbrainz_id TEXT,
                artist_norm TEXT,
                title_norm TEXT,
                album_norm TEXT,
                canonical_title TEXT,
                canonical_artist TEXT,
                canonical_album TEXT,
                canonical_genre TEXT,
                canonical_sub_genre TEXT,
                canonical_label TEXT,
                canonical_catalog_number TEXT,
                canonical_mix_name TEXT,
                canonical_duration REAL,
                canonical_year INTEGER,
                canonical_release_date TEXT,
                canonical_bpm REAL,
                canonical_key TEXT,
                canonical_payload_json TEXT,
                enriched_at TEXT,
                duration_ref_ms INTEGER,
                ref_source TEXT,
                merged_into_id INTEGER REFERENCES track_identity(id),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE schema_migrations (
                id INTEGER PRIMARY KEY,
                schema_name TEXT NOT NULL,
                version INTEGER NOT NULL,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
                note TEXT,
                UNIQUE(schema_name, version)
            );

            INSERT INTO schema_migrations (schema_name, version, note)
            VALUES ('v3', 5, 'dj profile support');

            CREATE INDEX idx_track_identity_isrc ON track_identity(isrc);
            CREATE INDEX idx_track_identity_beatport ON track_identity(beatport_id);
            CREATE INDEX idx_track_identity_tidal ON track_identity(tidal_id);
            CREATE INDEX idx_track_identity_qobuz ON track_identity(qobuz_id);
            CREATE INDEX idx_track_identity_musicbrainz ON track_identity(musicbrainz_id);
            CREATE INDEX idx_track_identity_merged_into ON track_identity(merged_into_id);
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_create_schema_v3_marks_version_6_and_adds_phase1_columns() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        create_schema_v3(conn)
        columns = _column_names(conn, "track_identity")
        versions = {
            int(row[0])
            for row in conn.execute(
                "SELECT version FROM schema_migrations WHERE schema_name='v3'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert V3_SCHEMA_VERSION == V3_SCHEMA_VERSION_CANONICAL_IDENTITY == 6
    assert {"label", "catalog_number", "canonical_duration_s"}.issubset(columns)
    assert 6 in versions


def test_run_pending_v3_upgrades_v5_fixture_and_verifies(tmp_path: Path) -> None:
    db_path = _create_v5_fixture(tmp_path)

    applied = run_pending_v3(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        columns = _column_names(conn, "track_identity")
        indexes = _index_names(conn)
        version = int(
            conn.execute(
                """
                SELECT MAX(version) FROM schema_migrations
                WHERE schema_name='v3'
                """
            ).fetchone()[0]
        )
        verify_v3_migration(conn)
    finally:
        conn.close()

    assert applied == ["0006_track_identity_phase1.py"]
    assert {"label", "catalog_number", "canonical_duration_s"}.issubset(columns)
    assert {
        "idx_track_identity_isrc_not_null",
        "idx_track_identity_beatport_not_null",
        "idx_track_identity_tidal_not_null",
        "idx_track_identity_qobuz_not_null",
        "idx_track_identity_musicbrainz_not_null",
        "idx_track_identity_merged_into_not_null",
        "idx_track_identity_artist_title_norm",
    }.issubset(indexes)
    assert version == 6


def test_merged_into_id_remains_nullable_after_0006(tmp_path: Path) -> None:
    db_path = _create_v5_fixture(tmp_path)
    run_pending_v3(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
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
    finally:
        conn.close()

    assert row is not None
    assert row[0] is None
    assert notnull["merged_into_id"] == 0
