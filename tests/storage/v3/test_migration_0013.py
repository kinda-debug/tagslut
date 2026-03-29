"""Tests for migration 0013: enforce provenance vocab checks on upgraded DBs."""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

_MIGRATION_DIR = Path(__file__).resolve().parents[3] / "tagslut" / "storage" / "v3" / "migrations"


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_0013",
        _MIGRATION_DIR / "0013_confidence_tier_update.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _create_pre_0013_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE schema_migrations (
            id INTEGER PRIMARY KEY,
            schema_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
            note TEXT,
            UNIQUE(schema_name, version)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE track_identity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identity_key TEXT NOT NULL UNIQUE,
            isrc TEXT,
            beatport_id TEXT,
            tidal_id TEXT,
            qobuz_id TEXT,
            spotify_id TEXT,
            apple_music_id TEXT,
            deezer_id TEXT,
            traxsource_id TEXT,
            itunes_id TEXT,
            musicbrainz_id TEXT,
            artist_norm TEXT,
            title_norm TEXT,
            album_norm TEXT,
            canonical_title TEXT,
            canonical_artist TEXT,
            canonical_album TEXT,
            canonical_genre TEXT,
            canonical_sub_genre TEXT,
            canonical_label TEXT,
            canonical_catalog_number TEXT,
            canonical_mix_name TEXT,
            canonical_duration REAL,
            canonical_year INTEGER,
            canonical_release_date TEXT,
            canonical_bpm REAL,
            canonical_key TEXT,
            canonical_payload_json TEXT,
            enriched_at TEXT,
            duration_ref_ms INTEGER,
            ref_source TEXT,
            ingested_at TEXT NOT NULL,
            ingestion_method TEXT NOT NULL,
            ingestion_source TEXT NOT NULL,
            ingestion_confidence TEXT NOT NULL,
            merged_into_id INTEGER REFERENCES track_identity(id),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE asset_file (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE asset_link (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            identity_id INTEGER NOT NULL,
            confidence REAL,
            link_source TEXT,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(asset_id),
            FOREIGN KEY(asset_id) REFERENCES asset_file(id) ON DELETE CASCADE,
            FOREIGN KEY(identity_id) REFERENCES track_identity(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_track_identity_merged_into ON track_identity(merged_into_id)")
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
    conn.execute(
        """
        INSERT INTO schema_migrations (schema_name, version, note)
        VALUES ('v3', 12, '0012_ingestion_provenance.py')
        """
    )
    conn.commit()
    return conn


def _seed_rows(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO track_identity (
            id, identity_key, beatport_id, ingested_at, ingestion_method, ingestion_source, ingestion_confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (1, "beatport:123", "123", "2026-03-22T00:00:00Z", "migration", "legacy_backfill", "legacy"),
    )
    conn.execute("INSERT INTO asset_file (id, path) VALUES (1, '/music/test.flac')")
    conn.execute(
        """
        INSERT INTO asset_link (asset_id, identity_id, confidence, link_source)
        VALUES (1, 1, 0.9, 'fixture')
        """
    )
    conn.commit()


def test_pre_migration_accepts_invalid_vocab() -> None:
    conn = _create_pre_0013_db()
    conn.execute(
        """
        INSERT INTO track_identity (
            identity_key, ingested_at, ingestion_method, ingestion_source, ingestion_confidence
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("test:invalid", "2026-03-22T00:00:00Z", "bogus_method", "fixture", "bogus_confidence"),
    )


def test_migration_enforces_new_vocab_and_preserves_fk_rows() -> None:
    mod = _load_migration()
    conn = _create_pre_0013_db()
    _seed_rows(conn)

    mod.up(conn)

    link_row = conn.execute("SELECT identity_id FROM asset_link WHERE asset_id = 1").fetchone()
    assert link_row is not None
    assert link_row["identity_id"] == 1
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO track_identity (
                identity_key, ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("test:bad_method", "2026-03-22T00:00:00Z", "bogus_method", "fixture", "high"),
        )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO track_identity (
                identity_key, ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("test:bad_conf", "2026-03-22T00:00:00Z", "migration", "fixture", "bogus_confidence"),
        )

    conn.execute(
        """
        INSERT INTO track_identity (
            identity_key, ingested_at, ingestion_method, ingestion_source, ingestion_confidence
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            "test:corroborated",
            "2026-03-22T00:00:00Z",
            "multi_provider_reconcile",
            "fixture",
            "corroborated",
        ),
    )


def test_records_schema_migration_and_is_idempotent() -> None:
    mod = _load_migration()
    conn = _create_pre_0013_db()
    _seed_rows(conn)

    mod.up(conn)
    mod.up(conn)

    row = conn.execute(
        "SELECT version, note FROM schema_migrations WHERE schema_name = 'v3' AND version = 13"
    ).fetchone()
    assert row is not None
    assert row["note"] == "0013_confidence_tier_update.py"

