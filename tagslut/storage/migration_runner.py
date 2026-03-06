from __future__ import annotations

import importlib.util
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Callable

logger = logging.getLogger("tagslut")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_migrations_applied_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migrations_applied (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            applied_at TEXT
        )
        """
    )


def _applied_migration_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM migrations_applied").fetchall()
    return {str(row[0]) for row in rows}


def _iter_migration_files(migrations_dir: Path) -> list[Path]:
    if not migrations_dir.exists():
        return []
    files = [
        path
        for path in migrations_dir.iterdir()
        if path.is_file()
        and path.suffix in {".sql", ".py"}
        and path.name != "__init__.py"
    ]
    return sorted(files, key=lambda p: p.name)


def _load_python_migration(path: Path) -> ModuleType:
    module_name = f"tagslut_storage_migration_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load migration module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _apply_sql_migration(conn: sqlite3.Connection, path: Path) -> None:
    sql_text = path.read_text(encoding="utf-8")
    conn.executescript(sql_text)


def _apply_python_migration(conn: sqlite3.Connection, path: Path) -> None:
    module = _load_python_migration(path)
    up = getattr(module, "up", None)
    if not callable(up):
        raise RuntimeError(f"Python migration must define up(conn): {path.name}")
    up_fn: Callable[[sqlite3.Connection], None] = up
    up_fn(conn)


def run_pending(db_path: str | Path, migrations_dir: Path | None = None) -> list[str]:
    """Apply pending SQL/Python migrations in filename order.

    Python migrations must export ``up(conn)``.
    """
    db_path_obj = Path(db_path)
    migrations_root = migrations_dir or MIGRATIONS_DIR
    applied_now: list[str] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    conn = sqlite3.connect(db_path_obj)
    try:
        with conn:
            _ensure_migrations_applied_table(conn)
        applied = _applied_migration_names(conn)

        for migration_path in _iter_migration_files(migrations_root):
            name = migration_path.name
            if name in applied:
                continue

            logger.info("Applying migration: %s", name)
            with conn:
                if migration_path.suffix == ".sql":
                    _apply_sql_migration(conn, migration_path)
                else:
                    _apply_python_migration(conn, migration_path)
                conn.execute(
                    "INSERT INTO migrations_applied (name, applied_at) VALUES (?, ?)",
                    (name, now),
                )
            applied_now.append(name)
            applied.add(name)

    finally:
        conn.close()

    return applied_now
