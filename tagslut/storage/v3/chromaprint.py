"""Helpers for v3 Chromaprint-backed identity resolution."""

from __future__ import annotations

import sqlite3

from tagslut.storage.schema import V3_ASSET_FILE_TABLE, V3_ASSET_LINK_TABLE


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def find_identity_by_fingerprint(
    conn: sqlite3.Connection,
    fingerprint: str | None,
    *,
    exclude_asset_id: int | None = None,
) -> int | None:
    """Resolve a single identity by exact Chromaprint fingerprint."""
    if not fingerprint:
        return None
    if not _column_exists(conn, V3_ASSET_FILE_TABLE, "chromaprint_fingerprint"):
        return None

    sql = f"""
        SELECT DISTINCT al.identity_id
        FROM {V3_ASSET_FILE_TABLE} af
        JOIN {V3_ASSET_LINK_TABLE} al
          ON al.asset_id = af.id
         AND al.active = 1
        WHERE af.chromaprint_fingerprint = ?
    """
    params: list[object] = [fingerprint]

    if exclude_asset_id is not None:
        sql += " AND af.id != ?"
        params.append(exclude_asset_id)

    rows = conn.execute(sql, tuple(params)).fetchall()
    identity_ids = [int(row[0]) for row in rows]

    if len(identity_ids) == 1:
        return identity_ids[0]
    return None
