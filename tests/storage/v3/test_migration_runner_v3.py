from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

from tagslut.storage.v3.db import open_db_v3
from tagslut.storage.v3.migration_runner import run_pending_v3


def _column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


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


def test_migration_0006_adds_canonical_track_identity_columns() -> None:
    module = importlib.import_module("tagslut.storage.v3.migrations.0006_track_identity_phase1")
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        conn.execute(
            """
            CREATE TABLE track_identity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_key TEXT NOT NULL UNIQUE,
                isrc TEXT,
                beatport_id TEXT,
                tidal_id TEXT,
                qobuz_id TEXT,
                musicbrainz_id TEXT,
                artist_norm TEXT,
                title_norm TEXT
            )
            """
        )

        module.up(conn)

        cols = set(_column_names(conn, "track_identity"))
        assert "canonical_label" in cols
        assert "canonical_catalog_number" in cols
        assert "canonical_duration" in cols
        assert "merged_into_id" in cols
        row = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE schema_name='v3' AND version=6"
        ).fetchone()
        assert row is not None
    finally:
        conn.close()


def test_migration_0007_renames_buggy_columns() -> None:
    module = importlib.import_module("tagslut.storage.v3.migrations.0007_track_identity_phase1_rename")
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        conn.execute(
            """
            CREATE TABLE track_identity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_key TEXT NOT NULL UNIQUE,
                label TEXT,
                catalog_number TEXT,
                canonical_duration_s REAL
            )
            """
        )

        module.up(conn)

        cols = set(_column_names(conn, "track_identity"))
        assert "canonical_label" in cols
        assert "canonical_catalog_number" in cols
        assert "canonical_duration" in cols
        assert "label" not in cols
        assert "catalog_number" not in cols
        assert "canonical_duration_s" not in cols
        row = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE schema_name='v3' AND version=7"
        ).fetchone()
        assert row is not None
    finally:
        conn.close()


def test_migration_0007_is_noop_when_canonical_columns_already_exist() -> None:
    module = importlib.import_module("tagslut.storage.v3.migrations.0007_track_identity_phase1_rename")
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        conn.execute(
            """
            CREATE TABLE track_identity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_key TEXT NOT NULL UNIQUE,
                canonical_label TEXT,
                canonical_catalog_number TEXT,
                canonical_duration REAL
            )
            """
        )

        module.up(conn)

        cols = set(_column_names(conn, "track_identity"))
        assert "canonical_label" in cols
        assert "canonical_catalog_number" in cols
        assert "canonical_duration" in cols
    finally:
        conn.close()


def test_migration_0007_rejects_old_sqlite(monkeypatch) -> None:
    module = importlib.import_module("tagslut.storage.v3.migrations.0007_track_identity_phase1_rename")
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        conn.execute(
            """
            CREATE TABLE track_identity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_key TEXT NOT NULL UNIQUE,
                label TEXT
            )
            """
        )
        monkeypatch.setattr(sqlite3, "sqlite_version", "3.24.0")
        try:
            module.up(conn)
            assert False, "expected RuntimeError for old SQLite"
        except RuntimeError as exc:
            assert "RENAME COLUMN requires SQLite >= 3.25.0" in str(exc)
        row = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE schema_name='v3' AND version=7"
        ).fetchone()
        assert row is None
        cols = set(_column_names(conn, "track_identity"))
        assert "label" in cols
        assert "canonical_label" not in cols
    finally:
        conn.close()


def test_migration_0008_creates_asset_analysis_and_export_view() -> None:
    module = importlib.import_module("tagslut.storage.v3.migrations.0008_asset_analysis")
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        conn.executescript(
            """
            CREATE TABLE track_identity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_key TEXT NOT NULL UNIQUE,
                isrc TEXT,
                canonical_artist TEXT,
                canonical_title TEXT,
                canonical_album TEXT,
                canonical_genre TEXT,
                canonical_label TEXT,
                canonical_year INTEGER,
                canonical_bpm REAL,
                canonical_key TEXT,
                merged_into_id INTEGER
            );
            CREATE TABLE asset_file (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE
            );
            CREATE TABLE preferred_asset (
                identity_id INTEGER PRIMARY KEY,
                asset_id INTEGER NOT NULL,
                score REAL NOT NULL,
                reason_json TEXT NOT NULL,
                version INTEGER NOT NULL
            );
            CREATE TABLE dj_track_profile (
                identity_id INTEGER PRIMARY KEY,
                energy INTEGER NULL
            );
            """
        )

        module.up(conn)

        table_row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='asset_analysis'"
        ).fetchone()
        view_row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_dj_export_metadata_v1'"
        ).fetchone()
        assert table_row is not None
        assert view_row is not None

        conn.execute(
            """
            INSERT INTO track_identity (
                id, identity_key, canonical_artist, canonical_title, canonical_label, canonical_bpm, canonical_key
            ) VALUES (1, 'id:1', 'Artist', 'Title', 'Label', 128, 'Am')
            """
        )
        conn.execute("INSERT INTO asset_file (id, path) VALUES (11, '/music/a.flac')")
        conn.execute(
            "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) VALUES (1, 11, 1, '{}', 1)"
        )
        row = conn.execute(
            "SELECT label, export_bpm, export_key FROM v_dj_export_metadata_v1 WHERE identity_id = 1"
        ).fetchone()
        assert row is not None
        assert row[0] == "Label"
        assert float(row[1]) == 128.0
        assert row[2] == "Am"

        conn.execute(
            """
            INSERT INTO asset_analysis (
                asset_id, analyzer, analyzer_version, analysis_scope, bpm, musical_key, analysis_energy_1_10
            ) VALUES (11, 'essentia', '1', 'dj', 120, 'Bm', 6)
            """
        )
        conn.execute(
            """
            INSERT INTO asset_analysis (
                asset_id, analyzer, analyzer_version, analysis_scope, bpm, musical_key, analysis_energy_1_10
            ) VALUES (11, 'essentia', '2', 'dj', 121, 'Cm', 7)
            """
        )
        count = conn.execute("SELECT COUNT(*) FROM asset_analysis").fetchone()[0]
        latest = conn.execute(
            "SELECT bpm, musical_key, analysis_energy_1_10 FROM asset_analysis WHERE asset_id = 11"
        ).fetchone()
        assert int(count) == 1
        assert latest is not None
        assert float(latest[0]) == 121.0
        assert latest[1] == "Cm"
        assert int(latest[2]) == 7
    finally:
        conn.close()


def test_run_pending_v3_uses_version_not_filename_count(tmp_path: Path) -> None:
    db_path = tmp_path / "music_v3.db"
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0006_old.py").write_text(
        "\n".join(
            [
                "VERSION = 6",
                "def up(conn):",
                "    conn.execute(\"CREATE TABLE IF NOT EXISTS never_runs (id INTEGER)\")",
            ]
        ),
        encoding="utf-8",
    )
    (migrations_dir / "0007_new.py").write_text(
        "\n".join(
            [
                "VERSION = 7",
                "def up(conn):",
                "    conn.execute(\"CREATE TABLE applied (id INTEGER PRIMARY KEY)\")",
                "    conn.execute(\"INSERT OR IGNORE INTO schema_migrations (schema_name, version, note) VALUES ('v3', 7, 'ok')\")",
            ]
        ),
        encoding="utf-8",
    )

    conn = open_db_v3(db_path)
    try:
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
        conn.execute(
            "INSERT INTO schema_migrations (schema_name, version, note) VALUES ('v3', 6, 'existing')"
        )
        conn.commit()
    finally:
        conn.close()

    applied = run_pending_v3(db_path, migrations_dir=migrations_dir)

    assert applied == ["0007_new.py"]
