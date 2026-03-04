from __future__ import annotations

import importlib.util
import shutil
import sqlite3
from pathlib import Path

import pytest

from tagslut.storage.migration_runner import run_pending

MIGRATION_NAME = "0005_zone_model_v2.py"


def _migration_source() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "tagslut"
        / "storage"
        / "migrations"
        / MIGRATION_NAME
    )


def _seed_zone_table(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE files (path TEXT PRIMARY KEY, zone TEXT)")
        conn.executemany(
            "INSERT INTO files (path, zone) VALUES (?, ?)",
            [
                ("/music/good.flac", "GOOD"),
                ("/music/bad.flac", "BAD"),
                ("/music/quarantine.flac", "QUARANTINE"),
                ("/music/accepted.flac", "accepted"),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _migration_dir_with_zone_migration(tmp_path: Path) -> Path:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    shutil.copy2(_migration_source(), migration_dir / MIGRATION_NAME)
    return migration_dir


def _read_zones(db_path: Path) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT path, zone FROM files ORDER BY path").fetchall()
    finally:
        conn.close()
    return {str(path): str(zone) for path, zone in rows}


def _load_migration_module(path: Path):
    spec = importlib.util.spec_from_file_location("zone_model_v2_migration", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load migration: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_zone_migration_converts_legacy_values(tmp_path: Path) -> None:
    db_path = tmp_path / "zones.sqlite"
    _seed_zone_table(db_path)

    applied = run_pending(db_path, migrations_dir=_migration_dir_with_zone_migration(tmp_path))

    assert applied == [MIGRATION_NAME]
    assert _read_zones(db_path) == {
        "/music/accepted.flac": "accepted",
        "/music/bad.flac": "archive",
        "/music/good.flac": "library",
        "/music/quarantine.flac": "archive",
    }


def test_zone_migration_runner_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "zones.sqlite"
    _seed_zone_table(db_path)
    migrations_dir = _migration_dir_with_zone_migration(tmp_path)

    first = run_pending(db_path, migrations_dir=migrations_dir)
    second = run_pending(db_path, migrations_dir=migrations_dir)

    assert first == [MIGRATION_NAME]
    assert second == []


def test_zone_migration_blocks_legacy_values_after_up(tmp_path: Path) -> None:
    db_path = tmp_path / "zones.sqlite"
    _seed_zone_table(db_path)

    run_pending(db_path, migrations_dir=_migration_dir_with_zone_migration(tmp_path))

    conn = sqlite3.connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO files (path, zone) VALUES (?, ?)",
                ("/music/new-good.flac", "GOOD"),
            )
    finally:
        conn.close()


def test_zone_migration_down_rolls_back_values(tmp_path: Path) -> None:
    db_path = tmp_path / "zones.sqlite"
    _seed_zone_table(db_path)
    migration_module = _load_migration_module(_migration_source())

    conn = sqlite3.connect(db_path)
    try:
        migration_module.up(conn)
        migration_module.down(conn)
        conn.commit()

        rows = conn.execute("SELECT path, zone FROM files ORDER BY path").fetchall()
    finally:
        conn.close()

    # Reverse mapping is intentionally lossy: both BAD and QUARANTINE map to BAD.
    assert {str(path): str(zone) for path, zone in rows} == {
        "/music/accepted.flac": "accepted",
        "/music/bad.flac": "BAD",
        "/music/good.flac": "GOOD",
        "/music/quarantine.flac": "BAD",
    }
