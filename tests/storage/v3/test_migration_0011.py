from __future__ import annotations

import importlib
import shutil
import sqlite3
from pathlib import Path

import pytest

from tagslut.storage.v3.migration_runner import run_pending_v3
from tagslut.storage.v3.schema import V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS_HARDENING


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
            apple_music_id TEXT,
            deezer_id TEXT,
            traxsource_id TEXT,
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


def test_migration_0011_duplicate_active_provider_ids_fail() -> None:
    module = importlib.import_module(
        "tagslut.storage.v3.migrations.0011_track_identity_provider_uniqueness_hardening"
    )
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        _create_track_identity(conn)
        conn.executemany(
            """
            INSERT INTO track_identity (identity_key, deezer_id, merged_into_id)
            VALUES (?, ?, ?)
            """,
            [
                ("deezer:1-a", "dz-1", None),
                ("deezer:1-b", " dz-1 ", None),
            ],
        )

        with pytest.raises(RuntimeError, match="duplicate active provider ids block migration 0011"):
            module.up(conn)
        duplicates = module.list_duplicate_active_provider_ids(conn)
        assert duplicates == [("deezer_id", "dz-1", 2)]
    finally:
        conn.close()


def test_migration_0011_merged_rows_do_not_block_canonical_winner_rows() -> None:
    module = importlib.import_module(
        "tagslut.storage.v3.migrations.0011_track_identity_provider_uniqueness_hardening"
    )
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        _create_track_identity(conn)
        conn.executemany(
            """
            INSERT INTO track_identity (id, identity_key, apple_music_id, merged_into_id)
            VALUES (?, ?, ?, ?)
            """,
            [
                (1, "apple:winner", "am-1", None),
                (2, "apple:loser", "am-1", 1),
            ],
        )

        module.up(conn)

        conn.execute(
            """
            INSERT INTO track_identity (identity_key, apple_music_id, merged_into_id)
            VALUES (?, ?, ?)
            """,
            ("apple:merged-dup", "am-1", 1),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO track_identity (identity_key, apple_music_id, merged_into_id)
                VALUES (?, ?, ?)
                """,
                ("apple:active-dup", "am-1", None),
            )
    finally:
        conn.close()


def test_migration_0011_null_and_blank_values_remain_allowed_after_normalization() -> None:
    module = importlib.import_module(
        "tagslut.storage.v3.migrations.0011_track_identity_provider_uniqueness_hardening"
    )
    conn = sqlite3.connect(":memory:")
    try:
        _create_schema_migrations(conn)
        _create_track_identity(conn)
        conn.executemany(
            """
            INSERT INTO track_identity (identity_key, apple_music_id, deezer_id, traxsource_id)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("id:blank-1", "   ", None, "\t"),
                ("id:blank-2", None, "  ", None),
            ],
        )

        module.up(conn)

        rows = conn.execute(
            """
            SELECT apple_music_id, deezer_id, traxsource_id
            FROM track_identity
            WHERE identity_key IN ('id:blank-1', 'id:blank-2')
            ORDER BY identity_key
            """
        ).fetchall()
        assert rows == [(None, None, None), (None, None, None)]

        conn.executemany(
            """
            INSERT INTO track_identity (identity_key, apple_music_id, deezer_id, traxsource_id)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("id:nulls", None, None, None),
                ("id:blanks", " ", " ", " "),
            ],
        )

        count = conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()
        assert count is not None
        assert int(count[0]) == 4
    finally:
        conn.close()


def test_migration_0011_applies_via_runner(tmp_path: Path) -> None:
    db_path = tmp_path / "provider_uniqueness_hardening.sqlite"
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    shutil.copy2(
        Path(__file__).resolve().parents[3]
        / "tagslut"
        / "storage"
        / "v3"
        / "migrations"
        / "0011_track_identity_provider_uniqueness_hardening.py",
        migrations_dir / "0011_track_identity_provider_uniqueness_hardening.py",
    )

    conn = sqlite3.connect(db_path)
    try:
        _create_schema_migrations(conn)
        _create_track_identity(conn)
        conn.execute(
            "INSERT INTO schema_migrations (schema_name, version, note) VALUES ('v3', 10, 'existing')"
        )
        conn.commit()
    finally:
        conn.close()

    applied = run_pending_v3(db_path, migrations_dir=migrations_dir)

    assert applied == ["0011_track_identity_provider_uniqueness_hardening.py"]

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE schema_name='v3' AND version=?",
            (V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS_HARDENING,),
        ).fetchone()
        assert row is not None
        sql = _index_sql(conn, "uq_track_identity_active_traxsource_id").lower()
        assert "create unique index" in sql
        assert "merged_into_id is null" in sql
    finally:
        conn.close()
