from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tagslut.storage.v3.migration_runner import run_pending_v3
from tagslut.storage.v3.schema import V3_SCHEMA_NAME, create_schema_v3


def test_run_pending_v3_applies_file_based_migration_once(tmp_path: Path) -> None:
    conn = sqlite3.connect(":memory:")
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "0006_add_test_marker.sql").write_text(
        "CREATE TABLE migration_test_marker (id INTEGER PRIMARY KEY);",
        encoding="utf-8",
    )

    try:
        create_schema_v3(conn)

        first = run_pending_v3(conn, migrations_dir=migration_dir)
        second = run_pending_v3(conn, migrations_dir=migration_dir)

        assert first == ["0006_add_test_marker.sql"]
        assert second == []
        row = conn.execute(
            "SELECT note FROM schema_migrations WHERE schema_name = ? AND version = 6",
            (V3_SCHEMA_NAME,),
        ).fetchone()
        assert row is not None
        assert row[0] == "0006_add_test_marker.sql"
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='migration_test_marker'"
        ).fetchone() is not None
    finally:
        conn.close()


def test_run_pending_v3_requires_base_schema() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(RuntimeError, match="v3 base schema missing required tables"):
            run_pending_v3(conn)
    finally:
        conn.close()
