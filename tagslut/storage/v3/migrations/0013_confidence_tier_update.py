"""Migration 0013: enforce five-tier ingestion confidence and method vocab."""

from __future__ import annotations

import sqlite3

SCHEMA_NAME = "v3"
VERSION = 13
NOTE = "0013_confidence_tier_update.py"

_TRACK_IDENTITY_SQL = """
CREATE TABLE track_identity_new (
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
    ingestion_method TEXT NOT NULL CHECK (
        ingestion_method IN (
            'provider_api',
            'isrc_lookup',
            'fingerprint_match',
            'fuzzy_text_match',
            'picard_tag',
            'manual',
            'migration',
            'multi_provider_reconcile'
        )
    ),
    ingestion_source TEXT NOT NULL,
    ingestion_confidence TEXT NOT NULL CHECK (
        ingestion_confidence IN ('verified','corroborated','high','uncertain','legacy')
    ),
    merged_into_id INTEGER REFERENCES track_identity(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""

_TRACK_IDENTITY_COLUMNS = [
    "id",
    "identity_key",
    "isrc",
    "beatport_id",
    "tidal_id",
    "qobuz_id",
    "spotify_id",
    "apple_music_id",
    "deezer_id",
    "traxsource_id",
    "itunes_id",
    "musicbrainz_id",
    "artist_norm",
    "title_norm",
    "album_norm",
    "canonical_title",
    "canonical_artist",
    "canonical_album",
    "canonical_genre",
    "canonical_sub_genre",
    "canonical_label",
    "canonical_catalog_number",
    "canonical_mix_name",
    "canonical_duration",
    "canonical_year",
    "canonical_release_date",
    "canonical_bpm",
    "canonical_key",
    "canonical_payload_json",
    "enriched_at",
    "duration_ref_ms",
    "ref_source",
    "ingested_at",
    "ingestion_method",
    "ingestion_source",
    "ingestion_confidence",
    "merged_into_id",
    "created_at",
    "updated_at",
]

_TRACK_IDENTITY_SUPPORT_SQL = """
CREATE INDEX IF NOT EXISTS idx_track_identity_key ON track_identity(identity_key);
CREATE INDEX IF NOT EXISTS idx_track_identity_isrc ON track_identity(isrc);
CREATE INDEX IF NOT EXISTS idx_track_identity_beatport ON track_identity(beatport_id);
CREATE INDEX IF NOT EXISTS idx_track_identity_tidal ON track_identity(tidal_id);
CREATE INDEX IF NOT EXISTS idx_track_identity_qobuz ON track_identity(qobuz_id);
CREATE INDEX IF NOT EXISTS idx_track_identity_spotify ON track_identity(spotify_id);
CREATE INDEX IF NOT EXISTS idx_track_identity_apple_music ON track_identity(apple_music_id);
CREATE INDEX IF NOT EXISTS idx_track_identity_deezer ON track_identity(deezer_id);
CREATE INDEX IF NOT EXISTS idx_track_identity_traxsource ON track_identity(traxsource_id);
CREATE INDEX IF NOT EXISTS idx_track_identity_itunes ON track_identity(itunes_id);
CREATE INDEX IF NOT EXISTS idx_track_identity_musicbrainz ON track_identity(musicbrainz_id);
CREATE INDEX IF NOT EXISTS idx_track_identity_ingested_at ON track_identity(ingested_at);
CREATE INDEX IF NOT EXISTS idx_track_identity_ingestion_method ON track_identity(ingestion_method);
CREATE INDEX IF NOT EXISTS idx_track_identity_ingestion_confidence ON track_identity(ingestion_confidence);
CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_beatport_id
    ON track_identity(beatport_id)
    WHERE beatport_id IS NOT NULL
      AND TRIM(beatport_id) != ''
      AND merged_into_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_tidal_id
    ON track_identity(tidal_id)
    WHERE tidal_id IS NOT NULL
      AND TRIM(tidal_id) != ''
      AND merged_into_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_qobuz_id
    ON track_identity(qobuz_id)
    WHERE qobuz_id IS NOT NULL
      AND TRIM(qobuz_id) != ''
      AND merged_into_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_spotify_id
    ON track_identity(spotify_id)
    WHERE spotify_id IS NOT NULL
      AND TRIM(spotify_id) != ''
      AND merged_into_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_apple_music_id
    ON track_identity(apple_music_id)
    WHERE apple_music_id IS NOT NULL
      AND TRIM(apple_music_id, ' \t\n\r') != ''
      AND merged_into_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_deezer_id
    ON track_identity(deezer_id)
    WHERE deezer_id IS NOT NULL
      AND TRIM(deezer_id, ' \t\n\r') != ''
      AND merged_into_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_traxsource_id
    ON track_identity(traxsource_id)
    WHERE traxsource_id IS NOT NULL
      AND TRIM(traxsource_id, ' \t\n\r') != ''
      AND merged_into_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_track_identity_merged_into ON track_identity(merged_into_id);
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
END;
"""


def _record_migration(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (SCHEMA_NAME, VERSION, NOTE),
    )


def _track_identity_sql(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'track_identity'
        """
    ).fetchone()
    return "" if row is None or row[0] is None else str(row[0])


def _already_enforced(conn: sqlite3.Connection) -> bool:
    sql = _track_identity_sql(conn)
    return "multi_provider_reconcile" in sql and "corroborated" in sql


def up(conn: sqlite3.Connection) -> None:
    if _already_enforced(conn):
        _record_migration(conn)
        return

    columns = ", ".join(_TRACK_IDENTITY_COLUMNS)
    previous_fk_state = conn.execute("PRAGMA foreign_keys").fetchone()
    foreign_keys_enabled = bool(previous_fk_state and previous_fk_state[0])

    if foreign_keys_enabled:
        conn.execute("PRAGMA foreign_keys = OFF")

    try:
        conn.execute(_TRACK_IDENTITY_SQL)
        conn.execute(
            f"""
            INSERT INTO track_identity_new ({columns})
            SELECT {columns}
            FROM track_identity
            """
        )
        conn.execute("DROP TABLE track_identity")
        conn.execute("ALTER TABLE track_identity_new RENAME TO track_identity")
        conn.executescript(_TRACK_IDENTITY_SUPPORT_SQL)
        _record_migration(conn)
    finally:
        if foreign_keys_enabled:
            conn.execute("PRAGMA foreign_keys = ON")
