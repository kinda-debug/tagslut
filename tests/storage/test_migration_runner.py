from __future__ import annotations

import sqlite3
from pathlib import Path

from tagslut.storage.migration_runner import run_pending


def _applied_names(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM migrations_applied ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def test_run_pending_on_empty_dir_creates_tracking_table(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()

    applied = run_pending(db_path, migrations_dir=migrations_dir)

    assert applied == []
    assert _applied_names(db_path) == []


def test_run_pending_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_create_table.sql").write_text(
        "CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT);",
        encoding="utf-8",
    )

    first = run_pending(db_path, migrations_dir=migrations_dir)
    second = run_pending(db_path, migrations_dir=migrations_dir)

    assert first == ["0001_create_table.sql"]
    assert second == []
    assert _applied_names(db_path) == ["0001_create_table.sql"]


def test_run_pending_applies_python_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_python_migration.py").write_text(
        "\n".join(
            [
                "def up(conn):",
                "    conn.execute(\"CREATE TABLE py_table (id INTEGER PRIMARY KEY, name TEXT)\")",
            ]
        ),
        encoding="utf-8",
    )

    applied = run_pending(db_path, migrations_dir=migrations_dir)

    assert applied == ["0001_python_migration.py"]
    conn = sqlite3.connect(db_path)
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='py_table'"
        ).fetchone()
    finally:
        conn.close()
    assert table is not None


def test_run_pending_applies_sql_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_create_and_insert.sql").write_text(
        """
        CREATE TABLE sql_table (id INTEGER PRIMARY KEY, value TEXT);
        INSERT INTO sql_table (value) VALUES ('ok');
        """,
        encoding="utf-8",
    )

    applied = run_pending(db_path, migrations_dir=migrations_dir)

    assert applied == ["0001_create_and_insert.sql"]
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT value FROM sql_table").fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "ok"


def test_run_pending_applies_in_filename_order(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "0001_init.sql").write_text(
        """
        CREATE TABLE ordering_log (ord INTEGER NOT NULL);
        INSERT INTO ordering_log (ord) VALUES (1);
        """,
        encoding="utf-8",
    )
    (migrations_dir / "0002_append.py").write_text(
        "\n".join(
            [
                "def up(conn):",
                "    conn.execute(\"INSERT INTO ordering_log (ord) VALUES (2)\")",
            ]
        ),
        encoding="utf-8",
    )

    applied = run_pending(db_path, migrations_dir=migrations_dir)

    assert applied == ["0001_init.sql", "0002_append.py"]
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT ord FROM ordering_log ORDER BY rowid").fetchall()
    finally:
        conn.close()
    assert [int(row[0]) for row in rows] == [1, 2]
