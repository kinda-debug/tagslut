from __future__ import annotations

import sqlite3
from pathlib import Path


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def resolve_latest_dj_export_path(
    conn: sqlite3.Connection,
    *,
    source_path: str | Path | None = None,
    identity_id: int | None = None,
) -> Path | None:
    if source_path is None and identity_id is None:
        raise ValueError("source_path or identity_id is required")
    if not _table_exists(conn, "provenance_event"):
        return None

    clauses = [
        "event_type = 'dj_export'",
        "dest_path IS NOT NULL",
        "(status IS NULL OR status = 'success')",
    ]
    params: list[object] = []
    if source_path is not None:
        clauses.append("source_path = ?")
        params.append(str(Path(source_path).expanduser().resolve()))
    if identity_id is not None:
        clauses.append("identity_id = ?")
        params.append(int(identity_id))

    row = conn.execute(
        f"""
        SELECT dest_path
        FROM provenance_event
        WHERE {" AND ".join(clauses)}
        ORDER BY COALESCE(event_time, '') DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    if row is None or not row[0]:
        return None
    return Path(str(row[0])).expanduser()
