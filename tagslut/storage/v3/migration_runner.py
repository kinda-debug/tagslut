from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from types import ModuleType
from typing import Callable

from tagslut.storage.v3.db import open_db_v3

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _iter_migration_files(migrations_dir: Path) -> list[Path]:
    if not migrations_dir.exists():
        return []
    files = [
        path
        for path in migrations_dir.iterdir()
        if path.is_file()
        and path.suffix == ".py"
        and path.name != "__init__.py"
    ]
    return sorted(files, key=lambda path: path.name)


def _load_migration(path: Path) -> ModuleType:
    module_name = f"tagslut_storage_v3_migration_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load v3 migration module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _schema_version(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "schema_migrations"):
        return 0
    row = conn.execute(
        """
        SELECT COALESCE(MAX(version), 0)
        FROM schema_migrations
        WHERE schema_name = 'v3'
        """
    ).fetchone()
    return int(row[0]) if row is not None and row[0] is not None else 0


def verify_v3_migration(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_rows:
        raise RuntimeError(f"foreign_key_check failed: {fk_rows!r}")
    integrity = conn.execute("PRAGMA integrity_check").fetchone()
    if integrity is None or str(integrity[0]).lower() != "ok":
        raise RuntimeError(f"integrity_check failed: {integrity!r}")
    conn.execute("PRAGMA optimize")


def run_pending_v3(db_path: str | Path, migrations_dir: Path | None = None) -> list[str]:
    applied: list[str] = []
    conn = open_db_v3(db_path)
    try:
        current_version = _schema_version(conn)
        for migration_path in _iter_migration_files(migrations_dir or MIGRATIONS_DIR):
            module = _load_migration(migration_path)
            migration_version = getattr(module, "VERSION", None)
            up = getattr(module, "up", None)
            if not isinstance(migration_version, int):
                raise RuntimeError(f"V3 migration must define integer VERSION: {migration_path.name}")
            if not callable(up):
                raise RuntimeError(f"V3 migration must define up(conn): {migration_path.name}")
            if migration_version <= current_version:
                continue
            up_fn: Callable[[sqlite3.Connection], None] = up
            with conn:
                up_fn(conn)
            applied.append(migration_path.name)
            current_version = migration_version
        verify_v3_migration(conn)
    finally:
        conn.close()
    return applied
