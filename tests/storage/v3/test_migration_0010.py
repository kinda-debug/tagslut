from __future__ import annotations

import importlib
import shutil
import sqlite3
from pathlib import Path

import pytest

from tagslut.storage.v3.migration_runner import run_pending_v3
from tagslut.storage.v3.schema import V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS


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


def _create_track_identity(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE track_identity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identity_key TEXT NOT NULL UNIQUE,
            beatport_id TEXT,
            tidal_id TEXT,
            qobuz_id TEXT,
            spotify_id TEXT,
            merged_into_id INTEGER REFERENCES track_identity(id)
        )
        """
    )


def _index_sql(conn: sqlite3.Connection, index_name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    ).fetchone()
    assert row is not None
    return str(row[0])


def test_migration_0010_duplicate_active_provider_ids_fail() -> None:
    module = importlib.import_module("tagslut.storage.v3.migrations.0010_track_identity_provider_uniqueness")
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        _create_track_identity(conn)
        conn.executemany(
            """
            INSERT INTO track_identity (identity_key, beatport_id, merged_into_id)
            VALUES (?, ?, ?)
            """,
            [
                ("beatport:1-a", "BP-1", None),
                ("beatport:1-b", "BP-1", None),
            ],
        )

        duplicates = module.list_duplicate_active_provider_ids(conn)

        assert duplicates == [("beatport_id", "BP-1", 2)]
        with pytest.raises(RuntimeError, match="duplicate active provider ids block migration 0010"):
            module.up(conn)
    finally:
        conn.close()


def test_migration_0010_merged_rows_do_not_block_canonical_winner_rows() -> None:
    module = importlib.import_module("tagslut.storage.v3.migrations.0010_track_identity_provider_uniqueness")
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        _create_track_identity(conn)
        conn.executemany(
            """
            INSERT INTO track_identity (id, identity_key, spotify_id, merged_into_id)
            VALUES (?, ?, ?, ?)
            """,
            [
                (1, "spotify:winner", "sp-1", None),
                (2, "spotify:loser", "sp-1", 1),
            ],
        )

        module.up(conn)

        conn.execute(
            """
            INSERT INTO track_identity (identity_key, spotify_id, merged_into_id)
            VALUES (?, ?, ?)
            """,
            ("spotify:merged-dup", "sp-1", 1),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO track_identity (identity_key, spotify_id, merged_into_id)
                VALUES (?, ?, ?)
                """,
                ("spotify:active-dup", "sp-1", None),
            )

        row = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE schema_name='v3' AND version=?",
            (module.VERSION,),
        ).fetchone()
        assert row is not None
    finally:
        conn.close()


def test_migration_0010_null_values_remain_allowed() -> None:
    module = importlib.import_module("tagslut.storage.v3.migrations.0010_track_identity_provider_uniqueness")
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        _create_track_identity(conn)

        module.up(conn)

        conn.executemany(
            """
            INSERT INTO track_identity (
                identity_key, beatport_id, tidal_id, qobuz_id, spotify_id, merged_into_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("id:nulls-1", None, None, None, None, None),
                ("id:nulls-2", None, None, None, None, None),
            ],
        )

        count = conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()
        assert count is not None
        assert int(count[0]) == 2
    finally:
        conn.close()


def test_migration_0010_applies_via_runner(tmp_path: Path) -> None:
    db_path = tmp_path / "provider_uniqueness.sqlite"
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    shutil.copy2(
        Path(__file__).resolve().parents[3]
        / "tagslut"
        / "storage"
        / "v3"
        / "migrations"
        / "0010_track_identity_provider_uniqueness.py",
        migrations_dir / "0010_track_identity_provider_uniqueness.py",
    )

    conn = sqlite3.connect(db_path)
    try:
        _create_schema_migrations(conn)
        _create_track_identity(conn)
        conn.execute(
            "INSERT INTO schema_migrations (schema_name, version, note) VALUES ('v3', 9, 'existing')"
        )
        conn.commit()
    finally:
        conn.close()

    applied = run_pending_v3(db_path, migrations_dir=migrations_dir)

    assert applied == ["0010_track_identity_provider_uniqueness.py"]

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE schema_name='v3' AND version=?",
            (V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS,),
        ).fetchone()
        assert row is not None
        sql = _index_sql(conn, "uq_track_identity_active_spotify_id").lower()
        assert "create unique index" in sql
        assert "merged_into_id is null" in sql
    finally:
        conn.close()
