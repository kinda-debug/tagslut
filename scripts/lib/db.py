"""Shared database helpers for dedupe scripts."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator, Sequence

DEFAULT_DB = Path("artifacts/db/library.db")


def _ensure_path(db_path: Path | str) -> Path:
    if isinstance(db_path, str):
        return Path(db_path)
    return db_path


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    """Open ``library.db`` and return a connection with row factory set."""
    path = _ensure_path(db_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def connect_context(db_path: Path | str = DEFAULT_DB) -> Iterator[sqlite3.Connection]:
    """Context manager that closes the connection automatically."""
    conn = connect(db_path)
    try:
        yield conn
    finally:
        conn.close()


def iter_library_rows(
    conn: sqlite3.Connection,
    *,
    root: str | None = None,
    checksum: str | None = None,
    columns: Sequence[str] | None = None,
    order_by: str | None = None,
) -> Iterator[sqlite3.Row]:
    """Yield rows from ``library_files`` optionally filtered by root/checksum."""
    default_columns = "path, checksum, duration, sample_rate, bit_rate, bit_depth"
    cols = ", ".join(columns) if columns else default_columns
    query = f"SELECT {cols} FROM library_files"
    filters: list[str] = []
    params: list[str] = []

    if checksum:
        filters.append("checksum = ?")
        params.append(checksum)

    if root:
        filters.append("path LIKE ?")
        params.append(f"{root.rstrip('/')}/%")

    if filters:
        query += f" WHERE {' AND '.join(filters)}"

    if order_by:
        query += f" ORDER BY {order_by}"

    cur = conn.execute(query, params)
    for row in cur:
        yield row


def rows_by_checksum(conn: sqlite3.Connection, checksum: str) -> Iterator[sqlite3.Row]:
    """Yield rows that share the same checksum."""
    yield from iter_library_rows(conn, checksum=checksum)


def rows_by_root(conn: sqlite3.Connection, root: str) -> Iterator[sqlite3.Row]:
    """Yield rows whose path starts with ``root``."""
    yield from iter_library_rows(conn, root=root)
