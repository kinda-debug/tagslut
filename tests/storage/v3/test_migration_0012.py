"""Tests for migration 0012: ingestion provenance columns on track_identity."""

from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest

_MIGRATION_DIR = Path(__file__).resolve().parents[3] / "tagslut" / "storage" / "v3" / "migrations"


def _load_migration():
    """Load migration 0012 module (name starts with digit, needs importlib)."""
    spec = importlib.util.spec_from_file_location(
        "migration_0012",
        _MIGRATION_DIR / "0012_ingestion_provenance.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _create_pre_0012_db() -> sqlite3.Connection:
    """Create a DB with track_identity but WITHOUT provenance columns."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE track_identity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identity_key TEXT NOT NULL UNIQUE,
            isrc TEXT,
            beatport_id TEXT,
            artist_norm TEXT,
            title_norm TEXT,
            ref_source TEXT,
            merged_into_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY,
            schema_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
            note TEXT,
            UNIQUE(schema_name, version)
        )
        """
    )
    conn.commit()
    return conn


def _seed_legacy_rows(conn: sqlite3.Connection) -> None:
    """Insert rows that simulate pre-provenance data."""
    conn.executemany(
        """
        INSERT INTO track_identity (id, identity_key, isrc, created_at)
        VALUES (?, ?, ?, ?)
        """,
        [
            (1, "isrc:US1234", "US1234", "2025-06-15T10:00:00Z"),
            (2, "beatport:9999", None, "2025-07-20T14:30:00Z"),
            (3, "text:artist|title", None, None),
        ],
    )
    conn.commit()


class TestMigration0012Upgrade:
    def test_adds_four_provenance_columns(self) -> None:
        mod = _load_migration()
        up = mod.up

        conn = _create_pre_0012_db()
        up(conn)

        cols = {row[1] for row in conn.execute("PRAGMA table_info(track_identity)").fetchall()}
        for col in ("ingested_at", "ingestion_method", "ingestion_source", "ingestion_confidence"):
            assert col in cols, f"Missing column: {col}"

    def test_backfills_existing_rows(self) -> None:
        mod = _load_migration()
        up = mod.up

        conn = _create_pre_0012_db()
        _seed_legacy_rows(conn)
        up(conn)

        rows = conn.execute(
            "SELECT id, ingested_at, ingestion_method, ingestion_source, ingestion_confidence FROM track_identity ORDER BY id"
        ).fetchall()

        # Row 1: had created_at, so ingested_at should inherit it
        assert rows[0]["ingested_at"] == "2025-06-15T10:00:00Z"
        assert rows[0]["ingestion_method"] == "migration"
        assert rows[0]["ingestion_source"] == "legacy_backfill"
        assert rows[0]["ingestion_confidence"] == "legacy"

        # Row 2: had created_at
        assert rows[1]["ingested_at"] == "2025-07-20T14:30:00Z"

        # Row 3: no created_at — falls back to datetime('now')
        assert rows[2]["ingested_at"] is not None
        assert rows[2]["ingestion_method"] == "migration"

    def test_creates_indexes(self) -> None:
        mod = _load_migration()
        up = mod.up

        conn = _create_pre_0012_db()
        up(conn)

        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(track_identity)").fetchall()
        }
        assert "idx_track_identity_ingested_at" in indexes
        assert "idx_track_identity_ingestion_method" in indexes
        assert "idx_track_identity_ingestion_confidence" in indexes

    def test_creates_enforcement_trigger(self) -> None:
        mod = _load_migration()
        up = mod.up

        conn = _create_pre_0012_db()
        up(conn)

        triggers = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='track_identity'"
        ).fetchall()
        trigger_names = {row[0] for row in triggers}
        assert "trg_track_identity_provenance_required" in trigger_names

    def test_records_schema_migration(self) -> None:
        mod = _load_migration()
        up = mod.up

        conn = _create_pre_0012_db()
        up(conn)

        row = conn.execute(
            "SELECT version, note FROM schema_migrations WHERE schema_name = 'v3' AND version = 12"
        ).fetchone()
        assert row is not None
        assert row["note"] == "0012_ingestion_provenance.py"

    def test_idempotent_upgrade(self) -> None:
        mod = _load_migration()
        up = mod.up

        conn = _create_pre_0012_db()
        _seed_legacy_rows(conn)
        up(conn)
        # Running again should not fail
        up(conn)

        count = conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0]
        assert count == 3


class TestProvenanceEnforcement:
    """Tests proving inserts fail when provenance is missing once enforcement is active."""

    def _enforced_db(self) -> sqlite3.Connection:
        from tagslut.storage.v3.schema import create_schema_v3

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        create_schema_v3(conn)
        return conn

    def test_insert_with_all_provenance_succeeds(self) -> None:
        conn = self._enforced_db()
        conn.execute(
            """
            INSERT INTO track_identity
                (identity_key, ingested_at, ingestion_method, ingestion_source, ingestion_confidence)
            VALUES
                ('test:ok', '2026-01-01T00:00:00Z', 'provider_api', 'test', 'high')
            """
        )
        row = conn.execute("SELECT * FROM track_identity WHERE identity_key = 'test:ok'").fetchone()
        assert row is not None

    def test_missing_ingested_at_fails(self) -> None:
        conn = self._enforced_db()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO track_identity
                    (identity_key, ingestion_method, ingestion_source, ingestion_confidence)
                VALUES
                    ('test:fail1', 'provider_api', 'test', 'high')
                """
            )

    def test_missing_ingestion_method_fails(self) -> None:
        conn = self._enforced_db()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO track_identity
                    (identity_key, ingested_at, ingestion_source, ingestion_confidence)
                VALUES
                    ('test:fail2', '2026-01-01T00:00:00Z', 'test', 'high')
                """
            )

    def test_missing_ingestion_source_fails(self) -> None:
        conn = self._enforced_db()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO track_identity
                    (identity_key, ingested_at, ingestion_method, ingestion_confidence)
                VALUES
                    ('test:fail3', '2026-01-01T00:00:00Z', 'provider_api', 'high')
                """
            )

    def test_missing_ingestion_confidence_fails(self) -> None:
        conn = self._enforced_db()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO track_identity
                    (identity_key, ingested_at, ingestion_method, ingestion_source)
                VALUES
                    ('test:fail4', '2026-01-01T00:00:00Z', 'provider_api', 'test')
                """
            )

    def test_empty_ingested_at_fails_trigger(self) -> None:
        conn = self._enforced_db()
        with pytest.raises(sqlite3.IntegrityError, match="ingested_at is required"):
            conn.execute(
                """
                INSERT INTO track_identity
                    (identity_key, ingested_at, ingestion_method, ingestion_source, ingestion_confidence)
                VALUES
                    ('test:fail5', '', 'provider_api', 'test', 'high')
                """
            )

    def test_empty_string_ingestion_source_allowed(self) -> None:
        """ingestion_source can be empty string but not NULL."""
        conn = self._enforced_db()
        conn.execute(
            """
            INSERT INTO track_identity
                (identity_key, ingested_at, ingestion_method, ingestion_source, ingestion_confidence)
            VALUES
                ('test:emptysrc', '2026-01-01T00:00:00Z', 'provider_api', '', 'high')
            """
        )
        row = conn.execute("SELECT ingestion_source FROM track_identity WHERE identity_key = 'test:emptysrc'").fetchone()
        assert row["ingestion_source"] == ""
