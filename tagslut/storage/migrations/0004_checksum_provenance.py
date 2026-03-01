"""Migration 0004: backfill files.checksum_type with inferred provenance."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row and int(row[0]) > 0)


class ChecksumProvenanceMigration:
    """Backfill helper retained for compatibility and targeted tests."""

    @staticmethod
    def get_pending_migrations(db_connection: sqlite3.Connection) -> int:
        try:
            cursor = db_connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM files WHERE checksum_type IS NULL")
            row = cursor.fetchone()
            return int(row[0]) if row else 0
        except Exception as e:
            logger.error("Failed to check pending migrations: %s", e)
            return 0

    @staticmethod
    def infer_checksum_type(file_record: dict[str, Any]) -> str:
        if file_record.get("streaminfo_md5"):
            return "STREAMINFO"
        if file_record.get("sha256"):
            return "SHA256"
        if file_record.get("md5"):
            return "STREAMINFO"
        checksum = str(file_record.get("checksum") or "")
        if checksum.startswith("sha256:"):
            return "SHA256"
        if checksum:
            return "STREAMINFO"
        return "UNKNOWN"

    @staticmethod
    def migrate_rows(db_connection: sqlite3.Connection) -> int:
        if not _table_exists(db_connection, "files"):
            return 0
        if not _table_has_column(db_connection, "files", "checksum_type"):
            return 0

        selectable = ["rowid", "checksum_type"]
        for optional_col in ("streaminfo_md5", "sha256", "md5", "checksum"):
            if _table_has_column(db_connection, "files", optional_col):
                selectable.append(optional_col)

        query = f"SELECT {', '.join(selectable)} FROM files WHERE checksum_type IS NULL"
        rows = db_connection.execute(query).fetchall()
        if not rows:
            return 0

        count = 0
        for row in rows:
            row_dict = dict(zip(selectable, row))
            checksum_type = ChecksumProvenanceMigration.infer_checksum_type(row_dict)
            db_connection.execute(
                "UPDATE files SET checksum_type = ? WHERE rowid = ?",
                (checksum_type, row_dict["rowid"]),
            )
            count += 1
        return count


def up(conn: sqlite3.Connection) -> None:
    migrated = ChecksumProvenanceMigration.migrate_rows(conn)
    logger.info("Migration 0004_checksum_provenance updated %d row(s)", migrated)
