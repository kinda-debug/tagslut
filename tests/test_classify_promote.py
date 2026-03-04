from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from tagslut.cli.main import cli
from tagslut.storage.classification_promotion import (
    PromotionError,
    promote_classification_v2,
)


def _create_files_db(db_path: Path, rows: list[tuple[str | None, str | None, str | None]]) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE files (
                id INTEGER PRIMARY KEY,
                classification TEXT,
                classification_v2 TEXT,
                genre TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO files (classification, classification_v2, genre) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _column_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("PRAGMA table_info(files)").fetchall()
        return {str(row[1]) for row in rows}
    finally:
        conn.close()


def test_promote_classification_dry_run_no_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    _create_files_db(
        db_path,
        [
            ("bar", "club", "House"),
            ("remove", "remove", "Techno"),
            ("club", "bar", ""),
        ],
    )

    result = promote_classification_v2(
        db_path,
        dry_run=True,
        sqlite_version_override="3.45.0",
    )
    assert result.status == "dry_run"
    assert result.method == "rename-column"
    assert "classification_v2" in _column_names(db_path)
    assert "classification_v1" not in _column_names(db_path)
    assert not Path(f"{db_path}.backup").exists()


def test_promote_classification_rename_path_success(tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    _create_files_db(
        db_path,
        [
            ("bar", "club", "House"),
            ("remove", "bar", "Techno"),
            ("club", "club", "Disco"),
        ],
    )

    result = promote_classification_v2(
        db_path,
        dry_run=False,
        sqlite_version_override="3.45.0",
    )
    assert result.status == "promoted"
    assert result.method == "rename-column"
    assert Path(f"{db_path}.backup").exists()

    cols = _column_names(db_path)
    assert "classification" in cols
    assert "classification_v1" in cols
    assert "classification_v2" not in cols

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT classification, classification_v1 FROM files ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    assert [tuple(row) for row in rows] == [
        ("club", "bar"),
        ("bar", "remove"),
        ("club", "club"),
    ]


def test_promote_classification_idempotent_second_run_noop(tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    _create_files_db(
        db_path,
        [
            ("bar", "club", "House"),
            ("club", "club", "Disco"),
        ],
    )

    first = promote_classification_v2(db_path, sqlite_version_override="3.45.0")
    second = promote_classification_v2(db_path, sqlite_version_override="3.45.0")

    assert first.status == "promoted"
    assert second.status == "already_promoted"
    assert "Already promoted" in second.message


def test_promote_classification_tripwire_remove_percent(tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    rows = [("bar", "remove", "House") for _ in range(9)] + [("bar", "club", "House")]
    _create_files_db(db_path, rows)

    with pytest.raises(PromotionError, match="remove%"):
        promote_classification_v2(
            db_path,
            sqlite_version_override="3.45.0",
        )

    cols = _column_names(db_path)
    assert "classification_v2" in cols
    assert "classification_v1" not in cols
    assert Path(f"{db_path}.backup").exists()


def test_promote_classification_classic_copy_path_for_old_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    _create_files_db(
        db_path,
        [
            ("bar", "club", "House"),
            ("club", "bar", "Techno"),
        ],
    )

    result = promote_classification_v2(
        db_path,
        sqlite_version_override="3.24.0",
    )
    assert result.status == "promoted"
    assert result.method == "classic-copy"

    cols = _column_names(db_path)
    assert "classification" in cols
    assert "classification_v1" in cols
    assert "classification_v2" not in cols

    conn = sqlite3.connect(str(db_path))
    try:
        archived_rows = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'files_pre_classification_promotion%'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert int(archived_rows) >= 1


def test_cli_promote_classification_dry_run_prints_plan(tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    _create_files_db(
        db_path,
        [
            ("bar", "club", "House"),
            ("club", "bar", "Techno"),
        ],
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["index", "promote-classification", "--db", str(db_path), "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "Status: dry_run" in result.output
    assert "Method: rename-column" in result.output
    assert "Dry-run only: no database changes were made." in result.output
