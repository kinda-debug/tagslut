"""
V3 SQLite migration runner.

Tracks applied migrations by numeric version in the `schema_migrations`
table under schema_name='v3'. Skips files whose names start with "_".
Runs PRAGMA foreign_key_check + integrity_check after each apply batch.

Python migration contract: module must export both:
  - `VERSION: int`  (numeric version, must be > current schema version)
  - `up(conn: sqlite3.Connection) -> None`

Does NOT handle ADD COLUMN IF NOT EXISTS — write standard ALTER TABLE.
Accepts a live sqlite3.Connection in addition to a db path.

See also: tagslut/storage/migration_runner.py (root runner, name-based tracking)
See also: tagslut/storage/base_migration_runner.py (divergence documentation)
"""

from __future__ import annotations

import importlib.util
import re
import sqlite3
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    def open_db_v3(db_path: str | Path) -> sqlite3.Connection: ...
else:
    from tagslut.storage.v3.db import open_db_v3

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_VERSION_PREFIX_RE = re.compile(r"^(?P<version>\d+)")


def _iter_migration_files(migrations_dir: Path) -> list[Path]:
    if not migrations_dir.exists():
        return []
    files = [
        path
        for path in migrations_dir.iterdir()
        if path.is_file()
        and path.suffix in {".py", ".sql"}
        and path.name != "__init__.py"
        and not path.name.startswith("_")
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


def _require_base_schema(conn: sqlite3.Connection) -> None:
    required = ("schema_migrations",)
    missing = [name for name in required if not _table_exists(conn, name)]
    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(f"v3 base schema missing required tables: {missing_text}")


def _version_from_filename(path: Path) -> int:
    match = _VERSION_PREFIX_RE.match(path.stem)
    if match is None:
        raise RuntimeError(f"V3 migration filename must start with a numeric version: {path.name}")
    return int(match.group("version"))


def _record_applied_version(conn: sqlite3.Connection, *, version: int, note: str) -> None:
    conn.execute(
        """
        INSERT INTO schema_migrations (schema_name, version, note)
        VALUES ('v3', ?, ?)
        ON CONFLICT(schema_name, version) DO UPDATE SET note = excluded.note
        """,
        (version, note),
    )


def _migration_recorded(conn: sqlite3.Connection, *, version: int, note: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM schema_migrations
        WHERE schema_name = 'v3' AND version = ? AND note = ?
        """,
        (version, note),
    ).fetchone()
    return row is not None


def _apply_sql_migration(conn: sqlite3.Connection, path: Path, *, version: int) -> None:
    conn.executescript(path.read_text(encoding="utf-8"))
    _record_applied_version(conn, version=version, note=path.name)


def verify_v3_migration(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_rows:
        raise RuntimeError(f"foreign_key_check failed: {fk_rows!r}")
    integrity = conn.execute("PRAGMA integrity_check").fetchone()
    if integrity is None or str(integrity[0]).lower() != "ok":
        raise RuntimeError(f"integrity_check failed: {integrity!r}")
    conn.execute("PRAGMA optimize")


def run_pending_v3(
    db_path: str | Path | sqlite3.Connection,
    migrations_dir: Path | None = None,
) -> list[str]:
    applied: list[str] = []
    if isinstance(db_path, sqlite3.Connection):
        owns_connection = False
        conn = db_path
    else:
        owns_connection = True
        conn = open_db_v3(db_path)
    try:
        _require_base_schema(conn)
        current_version = _schema_version(conn)
        for migration_path in _iter_migration_files(migrations_dir or MIGRATIONS_DIR):
            with conn:
                if migration_path.suffix == ".sql":
                    migration_version = _version_from_filename(migration_path)
                    if _migration_recorded(conn, version=migration_version, note=migration_path.name):
                        continue
                    _apply_sql_migration(conn, migration_path, version=migration_version)
                else:
                    module = _load_migration(migration_path)
                    migration_version = getattr(module, "VERSION", _version_from_filename(migration_path))
                    if not isinstance(migration_version, int):
                        raise RuntimeError(f"V3 migration VERSION must be an integer: {migration_path.name}")
                    if migration_version <= current_version:
                        continue
                    up = getattr(module, "up", None)
                    if not callable(up):
                        raise RuntimeError(f"V3 migration must define up(conn): {migration_path.name}")
                    up_fn: Callable[[sqlite3.Connection], None] = up
                    up_fn(conn)
                    _record_applied_version(conn, version=migration_version, note=migration_path.name)
            applied.append(migration_path.name)
            current_version = migration_version
        verify_v3_migration(conn)
    finally:
        if owns_connection:
            conn.close()
    return applied
