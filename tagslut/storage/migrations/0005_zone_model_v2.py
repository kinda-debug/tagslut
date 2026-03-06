"""Migration 0005: zone model v2 compatibility (GOOD/BAD/QUARANTINE -> library/archive)."""

from __future__ import annotations

import logging
import sqlite3


LEGACY_ZONE_TOKENS = ("GOOD", "BAD", "QUARANTINE")
INSERT_GUARD_TRIGGER = "trg_files_zone_block_legacy_insert"
UPDATE_GUARD_TRIGGER = "trg_files_zone_block_legacy_update"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row and int(row[0]) > 0)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _update_legacy_zone_values(conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE files SET zone = 'library' WHERE zone IS NOT NULL AND UPPER(TRIM(zone)) = 'GOOD'"
    )
    conn.execute(
        "UPDATE files SET zone = 'archive' WHERE zone IS NOT NULL AND UPPER(TRIM(zone)) = 'BAD'"
    )
    conn.execute(
        "UPDATE files SET zone = 'archive' WHERE zone IS NOT NULL AND UPPER(TRIM(zone)) = 'QUARANTINE'"
    )


def _create_zone_guards(conn: sqlite3.Connection) -> None:
    conn.execute(f"DROP TRIGGER IF EXISTS {INSERT_GUARD_TRIGGER}")
    conn.execute(f"DROP TRIGGER IF EXISTS {UPDATE_GUARD_TRIGGER}")

    conn.execute(
        f"""
        CREATE TRIGGER {INSERT_GUARD_TRIGGER}
        BEFORE INSERT ON files
        FOR EACH ROW
        WHEN NEW.zone IS NOT NULL AND UPPER(TRIM(NEW.zone)) IN ('GOOD', 'BAD', 'QUARANTINE')
        BEGIN
            SELECT RAISE(ABORT, 'legacy zone values are blocked: use library/djpool/archive');
        END;
        """
    )
    conn.execute(
        f"""
        CREATE TRIGGER {UPDATE_GUARD_TRIGGER}
        BEFORE UPDATE OF zone ON files
        FOR EACH ROW
        WHEN NEW.zone IS NOT NULL AND UPPER(TRIM(NEW.zone)) IN ('GOOD', 'BAD', 'QUARANTINE')
        BEGIN
            SELECT RAISE(ABORT, 'legacy zone values are blocked: use library/djpool/archive');
        END;
        """
    )


def _drop_zone_guards(conn: sqlite3.Connection) -> None:
    conn.execute(f"DROP TRIGGER IF EXISTS {INSERT_GUARD_TRIGGER}")
    conn.execute(f"DROP TRIGGER IF EXISTS {UPDATE_GUARD_TRIGGER}")


def up(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "files"):
        return
    if not _has_column(conn, "files", "zone"):
        return

    _update_legacy_zone_values(conn)
    _create_zone_guards(conn)


def down(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "files"):
        return
    if not _has_column(conn, "files", "zone"):
        return

    logging.getLogger(__name__).warning(
        "Zone migration rollback: ARCHIVE cannot be split back to BAD/QUARANTINE — no-op."
    )
