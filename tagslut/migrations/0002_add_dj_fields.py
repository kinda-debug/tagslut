"""Migration 0002: Add DJ metadata fields to the files table.

New columns
-----------
dj_flag          BOOLEAN (stored as INTEGER) DEFAULT 0  – marks a track as gig-worthy
dj_pool_path     TEXT                                   – path to derived MP3
bpm              REAL                                   – e.g. 132.5
key_camelot      TEXT                                   – e.g. '8A', '10B'
energy           INTEGER                                – 1-10
genre            TEXT
last_exported_usb TEXT (ISO timestamp)
rekordbox_id     INTEGER                                – written back from RB
isrc             TEXT (indexed)                         – promoted identity key

All columns are nullable / have safe defaults so the migration is non-destructive
on any existing database.

The ``up()`` method also back-fills ``bpm`` and ``key_camelot`` from the
canonical enrichment columns (``canonical_bpm``, ``canonical_key``) and from
raw tag JSON (``metadata_json``) where those values are already present.

The ``down()`` method drops the added columns using ``CREATE TABLE … AS SELECT``
round-trip (SQLite does not support ``ALTER TABLE … DROP COLUMN`` on all
supported versions, so this approach is universally safe).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

MIGRATION_ID = "0002_add_dj_fields"

# Columns added by this migration (name → DDL fragment)
_UP_COLUMNS: dict[str, str] = {
    "dj_flag": "INTEGER DEFAULT 0",
    "dj_pool_path": "TEXT",
    "bpm": "REAL",
    "key_camelot": "TEXT",
    "energy": "INTEGER",
    "genre": "TEXT",
    "last_exported_usb": "TEXT",
    "rekordbox_id": "INTEGER",
    "isrc": "TEXT",
}

_UP_INDICES: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_dj_flag ON files(dj_flag);",
    "CREATE INDEX IF NOT EXISTS idx_bpm ON files(bpm);",
    "CREATE INDEX IF NOT EXISTS idx_key_camelot ON files(key_camelot);",
    "CREATE INDEX IF NOT EXISTS idx_isrc ON files(isrc);",
    "CREATE INDEX IF NOT EXISTS idx_last_exported_usb ON files(last_exported_usb);",
    "CREATE INDEX IF NOT EXISTS idx_rekordbox_id ON files(rekordbox_id);",
    "CREATE INDEX IF NOT EXISTS idx_dj_pool_path ON files(dj_pool_path);",
]


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def up(conn: sqlite3.Connection) -> None:
    """Apply the migration: add DJ fields and back-fill where possible."""
    existing = _get_columns(conn, "files")

    with conn:
        for col_name, col_def in _UP_COLUMNS.items():
            if col_name not in existing:
                logger.info("Migration %s: adding column %s to files", MIGRATION_ID, col_name)
                conn.execute(f"ALTER TABLE files ADD COLUMN {col_name} {col_def}")

        for ddl in _UP_INDICES:
            conn.execute(ddl)

        # Back-fill bpm from canonical_bpm
        if "canonical_bpm" in existing and "bpm" in _UP_COLUMNS:
            conn.execute(
                "UPDATE files SET bpm = canonical_bpm "
                "WHERE bpm IS NULL AND canonical_bpm IS NOT NULL"
            )

        # Back-fill key_camelot from canonical_key
        if "canonical_key" in existing and "key_camelot" in _UP_COLUMNS:
            conn.execute(
                "UPDATE files SET key_camelot = canonical_key "
                "WHERE key_camelot IS NULL AND canonical_key IS NOT NULL"
            )

        # Back-fill isrc from canonical_isrc
        if "canonical_isrc" in existing and "isrc" in _UP_COLUMNS:
            conn.execute(
                "UPDATE files SET isrc = canonical_isrc "
                "WHERE isrc IS NULL AND canonical_isrc IS NOT NULL"
            )

        # Back-fill bpm / key_camelot from metadata_json where not yet populated
        if "metadata_json" in existing:
            _backfill_from_metadata_json(conn)

    logger.info("Migration %s: up complete", MIGRATION_ID)


def _backfill_from_metadata_json(conn: sqlite3.Connection) -> None:
    """Parse metadata_json to populate bpm / key_camelot for tracks that still lack them."""
    cursor = conn.execute(
        "SELECT path, metadata_json FROM files "
        "WHERE metadata_json IS NOT NULL AND (bpm IS NULL OR key_camelot IS NULL)"
    )
    rows = cursor.fetchall()
    updated = 0
    for path, metadata_json_str in rows:
        try:
            tags: dict = json.loads(metadata_json_str)  # type: ignore  # TODO: mypy-strict
        except (json.JSONDecodeError, TypeError):
            continue

        new_bpm: Optional[float] = None
        new_key: Optional[str] = None

        for bpm_key in ("BPM", "bpm", "TBPM", "tbpm"):
            raw = tags.get(bpm_key)
            if raw is not None:
                try:
                    new_bpm = float(str(raw).split(";")[0].strip())
                    break
                except (ValueError, TypeError):
                    pass

        for key_tag in ("TKEY", "key", "KEY", "initialkey", "INITIALKEY"):
            raw = tags.get(key_tag)
            if raw is not None:
                new_key = str(raw).strip()
                break

        if new_bpm is not None or new_key is not None:
            params: list = []  # type: ignore  # TODO: mypy-strict
            sets: list[str] = []
            if new_bpm is not None:
                sets.append("bpm = ?")
                params.append(new_bpm)
            if new_key is not None:
                sets.append("key_camelot = ?")
                params.append(new_key)
            params.append(path)
            conn.execute(f"UPDATE files SET {', '.join(sets)} WHERE path = ?", params)
            updated += 1

    if updated:
        logger.info("Migration %s: back-filled bpm/key_camelot for %d rows", MIGRATION_ID, updated)


def down(conn: sqlite3.Connection) -> None:
    """Reverse the migration: drop the DJ-specific columns added by up()."""
    existing = _get_columns(conn, "files")
    cols_to_drop = set(_UP_COLUMNS.keys()) & existing
    if not cols_to_drop:
        logger.info("Migration %s: nothing to roll back", MIGRATION_ID)
        return

    # Drop associated indices first
    index_names = [
        "idx_dj_flag", "idx_bpm", "idx_key_camelot", "idx_isrc",
        "idx_last_exported_usb", "idx_rekordbox_id", "idx_dj_pool_path",
    ]
    with conn:
        for idx in index_names:
            conn.execute(f"DROP INDEX IF EXISTS {idx}")

        # Attempt native DROP COLUMN (SQLite ≥ 3.35)
        try:
            for col in cols_to_drop:
                conn.execute(f"ALTER TABLE files DROP COLUMN {col}")
        except sqlite3.OperationalError:
            # Fallback: recreate the table without the dropped columns
            _drop_columns_via_recreate(conn, "files", cols_to_drop)

    logger.info("Migration %s: down complete", MIGRATION_ID)


def _drop_columns_via_recreate(
    conn: sqlite3.Connection,
    table: str,
    cols_to_drop: set[str],
) -> None:
    """Portable column-drop using CREATE TABLE … AS SELECT (SQLite ≤ 3.34 compatible)."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    all_cols = [row[1] for row in cursor.fetchall()]
    keep_cols = [c for c in all_cols if c not in cols_to_drop]
    col_list = ", ".join(keep_cols)

    conn.execute(f"CREATE TABLE _migration_tmp AS SELECT {col_list} FROM {table}")
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE _migration_tmp RENAME TO {table}")
