from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from tagslut.storage.migration_runner import run_pending


MIGRATION_NAME = "0008_add_dj_set_role.sql"


def _applied_names(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM migrations_applied ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [str(row[0]) for row in rows]


def test_dj_set_role_migration_applies_and_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "music.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE files (
                path TEXT PRIMARY KEY,
                checksum TEXT
            )
            """
        )
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
        / MIGRATION_NAME,
        migrations_dir / MIGRATION_NAME,
    )

    first = run_pending(db_path, migrations_dir=migrations_dir)
    second = run_pending(db_path, migrations_dir=migrations_dir)

    assert first == [MIGRATION_NAME]
    assert second == []
    assert _applied_names(db_path) == [MIGRATION_NAME]

    conn = sqlite3.connect(db_path)
    try:
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(files)")
        }
        indexes = {
            str(row[1])
            for row in conn.execute("PRAGMA index_list(files)")
        }
    finally:
        conn.close()

    assert "dj_set_role" in columns
    assert "dj_subrole" in columns
    assert "idx_dj_set_role" in indexes
    assert "idx_dj_subrole" in indexes
