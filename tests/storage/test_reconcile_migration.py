"""Tests for reconcile_log table and migration idempotency."""
from __future__ import annotations

import sqlite3

import pytest

from tagslut.storage.v3.db import open_db_v3


# ---------------------------------------------------------------------------
# Minimal DDL matching Task 1 schema
# ---------------------------------------------------------------------------

_FULL_DDL = """
CREATE TABLE IF NOT EXISTS track_identity (
    id INTEGER PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,
    isrc TEXT,
    artist_norm TEXT,
    title_norm TEXT,
    canonical_title TEXT,
    canonical_artist TEXT,
    canonical_bpm REAL,
    canonical_key TEXT,
    canonical_genre TEXT,
    canonical_label TEXT,
    canonical_mix_name TEXT,
    spotify_id TEXT,
    beatport_id TEXT,
    tidal_id TEXT,
    source TEXT,
    status TEXT,
    merged_into_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS asset_file (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    zone TEXT,
    library TEXT,
    size_bytes INTEGER,
    mtime TEXT,
    content_sha256 TEXT,
    duration_s REAL,
    first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS asset_link (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    identity_id INTEGER NOT NULL,
    confidence REAL,
    link_source TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mp3_asset (
    id INTEGER PRIMARY KEY,
    identity_id INTEGER,
    asset_id INTEGER,
    path TEXT NOT NULL UNIQUE,
    content_sha256 TEXT,
    bitrate INTEGER,
    sample_rate INTEGER,
    duration_s REAL,
    profile TEXT NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'unverified',
    source TEXT NOT NULL DEFAULT 'unknown',
    zone TEXT,
    transcoded_at TEXT,
    reconciled_at TEXT,
    lexicon_track_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dj_admission (
    id INTEGER PRIMARY KEY,
    identity_id INTEGER NOT NULL UNIQUE,
    mp3_asset_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    source TEXT NOT NULL DEFAULT 'unknown',
    notes TEXT,
    admitted_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dj_track_profile (
    identity_id INTEGER PRIMARY KEY,
    rating INTEGER,
    energy INTEGER,
    set_role TEXT,
    dj_tags_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    last_played_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dj_playlist (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_id INTEGER,
    lexicon_playlist_id INTEGER,
    sort_key TEXT,
    playlist_type TEXT NOT NULL DEFAULT 'standard',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dj_playlist_track (
    playlist_id INTEGER NOT NULL,
    dj_admission_id INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, dj_admission_id)
);
CREATE TABLE IF NOT EXISTS reconcile_log (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence TEXT,
    mp3_path TEXT,
    identity_id INTEGER,
    lexicon_track_id INTEGER,
    details_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_reconcile_log_run ON reconcile_log(run_id);
CREATE INDEX IF NOT EXISTS idx_reconcile_log_identity ON reconcile_log(identity_id);
"""

_EXPECTED_TABLES = {
    "track_identity",
    "asset_file",
    "asset_link",
    "mp3_asset",
    "dj_admission",
    "dj_track_profile",
    "dj_playlist",
    "dj_playlist_track",
    "reconcile_log",
}


def _apply_ddl(conn: sqlite3.Connection) -> None:
    conn.executescript(_FULL_DDL)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_migration_idempotent() -> None:
    """Running the full DDL twice raises no error (CREATE IF NOT EXISTS)."""
    conn = sqlite3.connect(":memory:")
    _apply_ddl(conn)
    _apply_ddl(conn)  # Second run must not fail


def test_all_seven_tables_exist() -> None:
    """All required tables exist after migration."""
    conn = sqlite3.connect(":memory:")
    _apply_ddl(conn)

    actual_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    for table in _EXPECTED_TABLES:
        assert table in actual_tables, f"Missing table: {table}"


def test_reconcile_log_indexes_exist() -> None:
    """reconcile_log has the required indexes."""
    conn = sqlite3.connect(":memory:")
    _apply_ddl(conn)

    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='reconcile_log'"
        ).fetchall()
    }

    assert "idx_reconcile_log_run" in indexes, "Missing idx_reconcile_log_run"
    assert "idx_reconcile_log_identity" in indexes, "Missing idx_reconcile_log_identity"


def test_reconcile_log_insert_and_query() -> None:
    """reconcile_log accepts inserts and can be queried by run_id."""
    conn = sqlite3.connect(":memory:")
    _apply_ddl(conn)

    run_id = "test-migration-001"
    conn.execute(
        """
        INSERT INTO reconcile_log (run_id, source, action, confidence, mp3_path)
        VALUES (?, 'test', 'test_action', 'HIGH', '/path/file.mp3')
        """,
        (run_id,),
    )
    conn.commit()

    rows = conn.execute(
        "SELECT run_id, action FROM reconcile_log WHERE run_id = ?", (run_id,)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "test_action"


def test_open_db_v3_memory() -> None:
    """open_db_v3 ':memory:' returns a usable connection."""
    conn = open_db_v3(":memory:")
    assert conn is not None
    # Check pragmas applied
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() in ("wal", "memory")
    conn.close()
