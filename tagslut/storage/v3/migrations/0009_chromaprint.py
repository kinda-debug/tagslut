"""Migration 0009: add Chromaprint storage to v3 asset_file."""

from __future__ import annotations

import sqlite3

from tagslut.storage.v3.schema import V3_SCHEMA_NAME, V3_SCHEMA_VERSION_CHROMAPRINT

VERSION = V3_SCHEMA_VERSION_CHROMAPRINT


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def up(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")

    if not _column_exists(conn, "asset_file", "chromaprint_fingerprint"):
        conn.execute("ALTER TABLE asset_file ADD COLUMN chromaprint_fingerprint TEXT")

    if not _column_exists(conn, "asset_file", "chromaprint_duration_s"):
        conn.execute("ALTER TABLE asset_file ADD COLUMN chromaprint_duration_s REAL")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_asset_file_chromaprint "
        "ON asset_file(chromaprint_fingerprint)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_asset_file_chromaprint_duration "
        "ON asset_file(chromaprint_duration_s)"
    )

    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (
            V3_SCHEMA_NAME,
            V3_SCHEMA_VERSION_CHROMAPRINT,
            "add chromaprint columns and indexes to asset_file",
        ),
    )
