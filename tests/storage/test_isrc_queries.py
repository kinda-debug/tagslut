from __future__ import annotations

import importlib.util
import shutil
import sqlite3
from pathlib import Path
from types import ModuleType

import pytest

from tagslut.storage.migration_runner import run_pending
from tagslut.storage.queries import get_file_by_isrc
from tagslut.storage.schema import init_db


def _load_migration() -> ModuleType:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "tagslut"
        / "storage"
        / "migrations"
        / "0006_isrc_unique_index.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0006", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _insert_track(
    conn: sqlite3.Connection,
    *,
    path: str,
    checksum: str,
    isrc: str | None = None,
    quality_rank: int = 4,
) -> None:
    conn.execute(
        """
        INSERT INTO files (
            path, checksum, metadata_json, quality_rank, isrc
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (path, checksum, "{}", quality_rank, isrc),
    )


@pytest.fixture
def mem_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    migration = _load_migration()
    migration.up(conn)
    conn.commit()
    yield conn
    conn.close()


def test_get_file_by_isrc_returns_inserted_row(mem_db: sqlite3.Connection) -> None:
    _insert_track(mem_db, path="/music/a.flac", checksum="a", isrc="USRC17607839", quality_rank=3)
    mem_db.commit()

    row = get_file_by_isrc(mem_db, "USRC17607839")

    assert row is not None
    assert row["path"] == "/music/a.flac"
    assert row["quality_rank"] == 3
    assert row["isrc"] == "USRC17607839"


def test_get_file_by_isrc_returns_none_for_missing_isrc(mem_db: sqlite3.Connection) -> None:
    _insert_track(mem_db, path="/music/no_isrc.flac", checksum="b", isrc=None)
    mem_db.commit()

    assert get_file_by_isrc(mem_db, "USRC99999999") is None


def test_get_file_by_isrc_with_none_returns_none_safely(mem_db: sqlite3.Connection) -> None:
    _insert_track(mem_db, path="/music/c.flac", checksum="c", isrc="USRC19800001")
    mem_db.commit()

    assert get_file_by_isrc(mem_db, None) is None
    assert get_file_by_isrc(mem_db, "   ") is None


def test_duplicate_isrc_insert_raises_integrity_error(mem_db: sqlite3.Connection) -> None:
    _insert_track(mem_db, path="/music/d1.flac", checksum="d1", isrc="USRC18880001")
    mem_db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        _insert_track(mem_db, path="/music/d2.flac", checksum="d2", isrc="USRC18880001")
        mem_db.commit()


def test_isrc_unique_index_exists_after_migration(mem_db: sqlite3.Connection) -> None:
    row = mem_db.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_files_isrc'"
    ).fetchone()

    assert row is not None
    sql = str(row["sql"]).lower()
    assert "create unique index" in sql
    assert "on files(isrc)" in sql
    assert "where isrc is not null" in sql


def test_isrc_migration_applies_via_runner(tmp_path: Path) -> None:
    db_path = tmp_path / "isrc.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        conn.commit()
    finally:
        conn.close()

    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    shutil.copy2(
        Path(__file__).resolve().parents[2]
        / "tagslut"
        / "storage"
        / "migrations"
        / "0006_isrc_unique_index.py",
        migrations_dir / "0006_isrc_unique_index.py",
    )

    applied = run_pending(db_path, migrations_dir=migrations_dir)

    assert applied == ["0006_isrc_unique_index.py"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_files_isrc'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
