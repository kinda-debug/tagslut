"""Tests for Migration 0002: add_dj_fields.

poetry run pytest tests/storage/test_dj_migration.py
"""

from __future__ import annotations

import importlib
import json
import sqlite3
from pathlib import Path
from types import ModuleType

import pytest

from tagslut.storage.schema import init_db


def _load_migration() -> ModuleType:
    """Load the 0002_add_dj_fields migration module via importlib."""
    spec = importlib.util.spec_from_file_location(
        "migration_0002",
        Path(__file__).parent.parent.parent
        / "tagslut" / "storage" / "migrations" / "0002_add_dj_fields.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def migration():
    return _load_migration()


@pytest.fixture
def bare_db():
    """A freshly-initialised in-memory database (no DJ columns yet)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def legacy_db():
    """Simulate a database that pre-dates the DJ columns."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Minimal files table without DJ columns
    conn.execute(
        """
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            checksum TEXT,
            canonical_bpm REAL,
            canonical_key TEXT,
            canonical_isrc TEXT,
            metadata_json TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO files (path, canonical_bpm, canonical_key, canonical_isrc) "
        "VALUES ('/music/track.flac', 132.5, '8A', 'USRC12345678')"
    )
    conn.execute(
        "INSERT INTO files (path, metadata_json) "
        "VALUES ('/music/track2.flac', ?)",
        (json.dumps({"BPM": "140", "TKEY": "10B"}),),
    )
    conn.commit()
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Tests: schema columns present after init_db
# ---------------------------------------------------------------------------


def test_init_db_creates_dj_flag(bare_db):
    cols = {row[1] for row in bare_db.execute("PRAGMA table_info(files)")}
    assert "dj_flag" in cols


def test_init_db_creates_bpm(bare_db):
    cols = {row[1] for row in bare_db.execute("PRAGMA table_info(files)")}
    assert "bpm" in cols


def test_init_db_creates_key_camelot(bare_db):
    cols = {row[1] for row in bare_db.execute("PRAGMA table_info(files)")}
    assert "key_camelot" in cols


def test_init_db_creates_energy(bare_db):
    cols = {row[1] for row in bare_db.execute("PRAGMA table_info(files)")}
    assert "energy" in cols


def test_init_db_creates_genre(bare_db):
    cols = {row[1] for row in bare_db.execute("PRAGMA table_info(files)")}
    assert "genre" in cols


def test_init_db_creates_isrc(bare_db):
    cols = {row[1] for row in bare_db.execute("PRAGMA table_info(files)")}
    assert "isrc" in cols


def test_init_db_creates_rekordbox_id(bare_db):
    cols = {row[1] for row in bare_db.execute("PRAGMA table_info(files)")}
    assert "rekordbox_id" in cols


def test_init_db_creates_last_exported_usb(bare_db):
    cols = {row[1] for row in bare_db.execute("PRAGMA table_info(files)")}
    assert "last_exported_usb" in cols


def test_init_db_creates_dj_pool_path(bare_db):
    cols = {row[1] for row in bare_db.execute("PRAGMA table_info(files)")}
    assert "dj_pool_path" in cols


# ---------------------------------------------------------------------------
# Tests: migration up() on legacy database
# ---------------------------------------------------------------------------


def test_up_adds_dj_columns(legacy_db, migration):
    migration.up(legacy_db)
    cols = {row[1] for row in legacy_db.execute("PRAGMA table_info(files)")}
    for expected in ("dj_flag", "bpm", "key_camelot", "energy", "genre", "isrc", "rekordbox_id"):
        assert expected in cols, f"Expected column '{expected}' missing after up()"


def test_up_backfills_bpm_from_canonical(legacy_db, migration):
    migration.up(legacy_db)
    row = legacy_db.execute(
        "SELECT bpm FROM files WHERE path = '/music/track.flac'"
    ).fetchone()
    assert row is not None
    assert row["bpm"] == 132.5


def test_up_backfills_key_camelot_from_canonical(legacy_db, migration):
    migration.up(legacy_db)
    row = legacy_db.execute(
        "SELECT key_camelot FROM files WHERE path = '/music/track.flac'"
    ).fetchone()
    assert row is not None
    assert row["key_camelot"] == "8A"


def test_up_backfills_isrc_from_canonical(legacy_db, migration):
    migration.up(legacy_db)
    row = legacy_db.execute(
        "SELECT isrc FROM files WHERE path = '/music/track.flac'"
    ).fetchone()
    assert row is not None
    assert row["isrc"] == "USRC12345678"


def test_up_backfills_bpm_from_metadata_json(legacy_db, migration):
    migration.up(legacy_db)
    row = legacy_db.execute(
        "SELECT bpm FROM files WHERE path = '/music/track2.flac'"
    ).fetchone()
    assert row is not None
    assert row["bpm"] == 140.0


def test_up_backfills_key_from_metadata_json(legacy_db, migration):
    migration.up(legacy_db)
    row = legacy_db.execute(
        "SELECT key_camelot FROM files WHERE path = '/music/track2.flac'"
    ).fetchone()
    assert row is not None
    assert row["key_camelot"] == "10B"


def test_up_dj_flag_defaults_to_zero(legacy_db, migration):
    migration.up(legacy_db)
    row = legacy_db.execute(
        "SELECT dj_flag FROM files WHERE path = '/music/track.flac'"
    ).fetchone()
    assert row is not None
    assert row["dj_flag"] == 0


def test_up_is_idempotent(legacy_db, migration):
    """Running up() twice must not raise."""
    migration.up(legacy_db)
    migration.up(legacy_db)


# ---------------------------------------------------------------------------
# Tests: migration down() reverses up()
# ---------------------------------------------------------------------------


def test_down_removes_dj_columns(legacy_db, migration):
    migration.up(legacy_db)
    migration.down(legacy_db)
    cols = {row[1] for row in legacy_db.execute("PRAGMA table_info(files)")}
    for dropped in ("dj_flag", "bpm", "key_camelot", "energy", "genre", "isrc", "rekordbox_id"):
        assert dropped not in cols, f"Column '{dropped}' should have been dropped by down()"


def test_down_preserves_original_columns(legacy_db, migration):
    migration.up(legacy_db)
    migration.down(legacy_db)
    cols = {row[1] for row in legacy_db.execute("PRAGMA table_info(files)")}
    for original in ("path", "checksum", "canonical_bpm", "canonical_key"):
        assert original in cols, f"Original column '{original}' was incorrectly removed by down()"


def test_down_is_idempotent(legacy_db, migration):
    """Running down() twice (or without prior up()) must not raise."""
    migration.up(legacy_db)
    migration.down(legacy_db)
    migration.down(legacy_db)


# ---------------------------------------------------------------------------
# Tests: DJ flag CRUD via raw SQL (exercises the schema surface used by CLI)
# ---------------------------------------------------------------------------


def test_dj_flag_can_be_set(bare_db):
    bare_db.execute(
        "INSERT OR IGNORE INTO files (path, checksum) VALUES ('/music/a.flac', 'abc')"
    )
    bare_db.execute("UPDATE files SET dj_flag = 1 WHERE path = '/music/a.flac'")
    bare_db.commit()
    row = bare_db.execute(
        "SELECT dj_flag FROM files WHERE path = '/music/a.flac'"
    ).fetchone()
    assert row["dj_flag"] == 1


def test_dj_autoflag_by_bpm_range(bare_db):
    bare_db.execute(
        "INSERT OR IGNORE INTO files (path, checksum, bpm) VALUES ('/music/b.flac', 'def', 130.0)"
    )
    bare_db.execute(
        "INSERT OR IGNORE INTO files (path, checksum, bpm) VALUES ('/music/c.flac', 'ghi', 90.0)"
    )
    bare_db.execute("UPDATE files SET dj_flag = 1 WHERE bpm BETWEEN 125 AND 145")
    bare_db.commit()
    rows = bare_db.execute("SELECT path, dj_flag FROM files ORDER BY path").fetchall()
    flagged = {row["path"] for row in rows if row["dj_flag"] == 1}
    assert "/music/b.flac" in flagged
    assert "/music/c.flac" not in flagged


def test_dj_status_query_returns_flagged(bare_db):
    bare_db.execute(
        "INSERT OR IGNORE INTO files (path, checksum, dj_flag, bpm, key_camelot) "
        "VALUES ('/music/d.flac', 'jkl', 1, 132.5, '8A')"
    )
    bare_db.commit()
    rows = bare_db.execute(
        "SELECT path, bpm, key_camelot FROM files WHERE dj_flag = 1"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["bpm"] == 132.5
    assert rows[0]["key_camelot"] == "8A"
