"""Migration 0012: Add ingestion provenance columns to track_identity.

Adds four mandatory provenance fields and backfills existing rows with
'migration' / 'legacy' defaults.  An enforcement trigger rejects future
INSERTs that omit any of the four fields.
"""

from __future__ import annotations

import sqlite3

SCHEMA_NAME = "v3"
VERSION = 12


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def up(conn: sqlite3.Connection) -> None:
    # --- 1. Add columns (idempotent) ---
    for col in ("ingested_at", "ingestion_method", "ingestion_source", "ingestion_confidence"):
        if not _column_exists(conn, "track_identity", col):
            conn.execute(f"ALTER TABLE track_identity ADD COLUMN {col} TEXT")

    # --- 2. Backfill existing rows ---
    conn.execute(
        """
        UPDATE track_identity
        SET
            ingested_at       = COALESCE(ingested_at, created_at, datetime('now')),
            ingestion_method  = COALESCE(ingestion_method, 'migration'),
            ingestion_source  = COALESCE(ingestion_source, 'legacy_backfill'),
            ingestion_confidence = COALESCE(ingestion_confidence, 'legacy')
        WHERE ingested_at IS NULL
           OR ingestion_method IS NULL
           OR ingestion_source IS NULL
           OR ingestion_confidence IS NULL
        """
    )

    # --- 3. Indexes ---
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_track_identity_ingested_at "
        "ON track_identity(ingested_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_track_identity_ingestion_method "
        "ON track_identity(ingestion_method)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_track_identity_ingestion_confidence "
        "ON track_identity(ingestion_confidence)"
    )

    # --- 4. Enforcement trigger ---
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_track_identity_provenance_required
        BEFORE INSERT ON track_identity
        BEGIN
            SELECT CASE
                WHEN NEW.ingested_at IS NULL OR TRIM(NEW.ingested_at) = '' THEN
                    RAISE(ABORT, 'track_identity.ingested_at is required')
                WHEN NEW.ingestion_method IS NULL OR TRIM(NEW.ingestion_method) = '' THEN
                    RAISE(ABORT, 'track_identity.ingestion_method is required')
                WHEN NEW.ingestion_source IS NULL THEN
                    RAISE(ABORT, 'track_identity.ingestion_source is required')
                WHEN NEW.ingestion_confidence IS NULL OR TRIM(NEW.ingestion_confidence) = '' THEN
                    RAISE(ABORT, 'track_identity.ingestion_confidence is required')
            END;
        END
        """
    )

    # --- 5. Record migration ---
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (SCHEMA_NAME, VERSION, "0012_ingestion_provenance.py"),
    )
    conn.commit()
