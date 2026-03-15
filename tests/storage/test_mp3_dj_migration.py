"""Tests for the authoritative DJ pipeline layout — verifies all new tables
and indexes are created correctly and that the migration is idempotent."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tagslut.storage.schema import init_db


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _index_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }


def test_migration_creates_mp3_asset_table(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    init_db(conn)
    conn.commit()
    assert "mp3_asset" in _table_names(conn)


def test_migration_creates_dj_admission_table(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    init_db(conn)
    conn.commit()
    assert "dj_admission" in _table_names(conn)


def test_migration_creates_dj_track_id_map_table(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    init_db(conn)
    conn.commit()
    assert "dj_track_id_map" in _table_names(conn)


def test_migration_creates_dj_playlist_tables(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    init_db(conn)
    conn.commit()
    tables = _table_names(conn)
    assert "dj_playlist" in tables
    assert "dj_playlist_track" in tables


def test_migration_creates_dj_export_state_table(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    init_db(conn)
    conn.commit()
    assert "dj_export_state" in _table_names(conn)


def test_migration_creates_mp3_asset_indexes(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    init_db(conn)
    conn.commit()
    indexes = _index_names(conn)
    assert "idx_mp3_asset_identity" in indexes
    assert "idx_mp3_asset_zone" in indexes
    assert "idx_mp3_asset_lexicon" in indexes


def test_migration_creates_dj_admission_indexes(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    init_db(conn)
    conn.commit()
    indexes = _index_names(conn)
    assert "idx_dj_admission_identity" in indexes
def test_migration_is_idempotent(tmp_path: Path) -> None:
    """Running init_db twice on the same database must not raise."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.commit()
    conn.close()

    conn2 = sqlite3.connect(str(db_path))
    init_db(conn2)  # must not raise
    conn2.commit()
    conn2.close()


def test_mp3_asset_foreign_key_constraints(tmp_path: Path) -> None:
    """mp3_asset foreign keys must reference valid track_identity and asset_file rows."""
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO mp3_asset
              (identity_id, asset_id, profile, path, status)
            VALUES (9999, 9999, 'mp3_320_cbr', '/tmp/bad.mp3', 'verified')
            """
        )
        conn.commit()
