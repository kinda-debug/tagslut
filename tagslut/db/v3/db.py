"""SQLite connection helper for standalone v3 databases."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def open_db_v3(path: str | Path, create: bool = True) -> sqlite3.Connection:
    """Open a v3 SQLite database and apply required pragmas.

    Pragmas:
    - foreign_keys=ON
    - journal_mode=WAL
    - synchronous=NORMAL
    """
    if str(path) == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        db_path = Path(path).expanduser()
        if not db_path.exists():
            if not create:
                raise FileNotFoundError(f"DB not found: {db_path}")
            db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

