"""Read-only structural checks for standalone v3 databases."""

from __future__ import annotations

import sqlite3
from typing import Any

REQUIRED_V3_TABLES = ("asset_file", "track_identity", "asset_link")
REQUIRED_V3_COUNT_COLUMNS: dict[str, tuple[str, ...]] = {
    "asset_file": ("path", "integrity_checked_at", "sha256_checked_at"),
    "track_identity": ("identity_key", "enriched_at"),
    "asset_link": ("asset_id", "identity_id"),
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {str(row[1]) for row in rows}


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0]) if row else 0


def _count_non_empty(conn: sqlite3.Connection, table: str, column: str) -> int:
    row = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL AND TRIM({column}) != ''"
    ).fetchone()
    return int(row[0]) if row else 0


def doctor_v3(conn: sqlite3.Connection) -> dict[str, Any]:
    """Run v3-only structural checks and return a structured result."""
    errors: list[str] = []

    conn.execute("PRAGMA foreign_keys=ON")
    foreign_keys = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    if foreign_keys != 1:
        errors.append("v3 PRAGMA foreign_keys must be 1")

    has_legacy_files_table = _table_exists(conn, "files")
    if has_legacy_files_table:
        errors.append("v3 schema must not include legacy table: files")

    missing_tables = [table for table in REQUIRED_V3_TABLES if not _table_exists(conn, table)]
    if missing_tables:
        errors.append("missing v3 tables: " + ", ".join(missing_tables))

    missing_columns: dict[str, list[str]] = {}
    for table, required_columns in REQUIRED_V3_COUNT_COLUMNS.items():
        if table in missing_tables:
            continue
        columns = _get_columns(conn, table)
        missing = sorted(col for col in required_columns if col not in columns)
        if missing:
            missing_columns[table] = missing
    if missing_columns:
        for table, missing in sorted(missing_columns.items()):
            errors.append(f"v3.{table} missing columns: {', '.join(missing)}")

    counts = {
        "asset_file_total": 0,
        "asset_link_total": 0,
        "track_identity_total": 0,
        "integrity_done": 0,
        "sha256_done": 0,
        "enriched_done": 0,
    }
    if not missing_tables and not missing_columns:
        counts["asset_file_total"] = _count_rows(conn, "asset_file")
        counts["asset_link_total"] = _count_rows(conn, "asset_link")
        counts["track_identity_total"] = _count_rows(conn, "track_identity")
        counts["integrity_done"] = _count_non_empty(conn, "asset_file", "integrity_checked_at")
        counts["sha256_done"] = _count_non_empty(conn, "asset_file", "sha256_checked_at")
        counts["enriched_done"] = _count_non_empty(conn, "track_identity", "enriched_at")
        if counts["asset_file_total"] != counts["asset_link_total"]:
            errors.append(
                "invariant failed: COUNT(asset_file) must equal COUNT(asset_link)"
            )

    return {
        "ok": not errors,
        "errors": errors,
        "counts": counts,
        "foreign_keys": foreign_keys,
        "has_legacy_files_table": has_legacy_files_table,
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
    }
