from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tagslut.storage.v3.db import open_db_v3
from tagslut.storage.v3.schema import create_schema_v3
from tagslut.storage.schema import init_db


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def _index_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    return {str(row[0]) for row in rows}


def test_create_schema_v3_creates_required_tables_without_v2_files() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        create_schema_v3(conn)
        names = _table_names(conn)
    finally:
        conn.close()

    required = {
        "asset_file",
        "track_identity",
        "asset_link",
        "asset_analysis",
        "preferred_asset",
        "identity_status",
        "library_track_sources",
        "move_plan",
        "move_execution",
        "provenance_event",
        "scan_runs",
        "scan_queue",
        "scan_issues",
        "identity_evidence",
        "identity_resolution_run",
        "identity_resolution_candidate",
        "identity_duplicate_cohort",
        "identity_duplicate_cohort_member",
        "recording_cluster",
        "schema_migrations",
    }
    assert required.issubset(names)
    assert "files" not in names


def test_track_identity_identity_key_is_unique_and_not_null() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        create_schema_v3(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO track_identity (identity_key, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (NULL, '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')")

        conn.execute("INSERT INTO track_identity (identity_key, isrc, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, ?, '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')", ("isrc:abc", "ABC"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO track_identity (identity_key, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')", ("isrc:abc",))
    finally:
        conn.close()


def test_foreign_keys_enforced_for_asset_link_and_library_track_sources() -> None:
    conn = open_db_v3(":memory:")
    try:
        create_schema_v3(conn)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO asset_link (asset_id, identity_id, confidence, link_source)
                VALUES (1, 1, 1.0, 'test')
                """
            )

        conn.execute("INSERT INTO asset_file (path) VALUES (?)", ("/music/a.flac",))
        conn.execute("INSERT INTO track_identity (identity_key, isrc, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, ?, '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')", ("isrc:a", "A"))
        asset_id = int(conn.execute("SELECT id FROM asset_file").fetchone()[0])
        identity_id = int(conn.execute("SELECT id FROM track_identity").fetchone()[0])
        conn.execute(
            """
            INSERT INTO asset_link (asset_id, identity_id, confidence, link_source)
            VALUES (?, ?, 1.0, 'register')
            """,
            (asset_id, identity_id),
        )

        conn.execute("INSERT INTO track_identity (identity_key, isrc, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, ?, '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')", ("isrc:b", "B"))
        other_identity_id = int(
            conn.execute("SELECT id FROM track_identity WHERE identity_key = 'isrc:b'").fetchone()[0]
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO asset_link (asset_id, identity_id, confidence, link_source)
                VALUES (?, ?, 0.5, 'relink')
                """,
                (asset_id, other_identity_id),
            )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO library_track_sources (identity_key, provider, provider_track_id)
                VALUES (?, ?, ?)
                """,
                ("isrc:missing", "beatport", "123"),
            )

        conn.execute(
            """
            INSERT INTO library_track_sources (identity_key, provider, provider_track_id)
            VALUES (?, ?, ?)
            """,
            ("isrc:a", "beatport", "123"),
        )
    finally:
        conn.close()


def test_open_db_v3_sets_required_pragmas(tmp_path: Path) -> None:
    db_path = tmp_path / "music_v3.db"
    conn = open_db_v3(db_path, create=True)
    try:
        foreign_keys = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
        journal_mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        synchronous = int(conn.execute("PRAGMA synchronous").fetchone()[0])
    finally:
        conn.close()

    assert foreign_keys == 1
    assert journal_mode == "wal"
    assert synchronous == 1  # NORMAL


def test_open_db_v3_create_false_requires_existing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        open_db_v3(tmp_path / "missing_v3.db", create=False)


def test_create_schema_v3_creates_expected_indexes() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        create_schema_v3(conn)
        names = _index_names(conn)
    finally:
        conn.close()

    expected = {
        "idx_asset_file_sha256",
        "idx_asset_file_streaminfo_md5",
        "idx_asset_file_checksum",
        "idx_track_identity_key",
        "idx_track_identity_isrc",
        "idx_track_identity_beatport",
        "idx_track_identity_tidal",
        "idx_track_identity_qobuz",
        "idx_track_identity_spotify",
        "idx_track_identity_apple_music",
        "idx_track_identity_deezer",
        "idx_track_identity_traxsource",
        "idx_track_identity_itunes",
        "idx_preferred_asset_asset_id",
        "idx_identity_status_status",
        "idx_library_track_sources_provider_id",
        "idx_move_execution_status",
    }
    assert expected.issubset(names)


def test_create_schema_v3_creates_active_identity_view() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        create_schema_v3(conn)
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_active_identity'"
        ).fetchone()
        export_view = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_dj_export_metadata_v1'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert export_view is not None


def test_init_db_is_compatible_with_v3_library_track_sources_shape() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        create_schema_v3(conn)
        init_db(conn)
    finally:
        conn.close()


def test_create_schema_v3_accepts_spotify_intake_ingestion_method() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        create_schema_v3(conn)
        conn.execute(
            """
            INSERT INTO track_identity (
                identity_key,
                spotify_id,
                ingested_at,
                ingestion_method,
                ingestion_source,
                ingestion_confidence
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "spotify:abc123",
                "abc123",
                "2026-04-03T00:00:00+00:00",
                "spotify_intake",
                "spotiflac:https://open.spotify.com/track/abc123|service:qobuz",
                "high",
            ),
        )
    finally:
        conn.close()
