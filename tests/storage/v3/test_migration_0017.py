from __future__ import annotations

import sqlite3

from tagslut.storage.v3.migration_runner import run_pending_v3


_OLD_TRACK_IDENTITY_SQL = """
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


def test_migration_0017_allows_spotify_intake() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(
            """
            CREATE TABLE schema_migrations (
                id INTEGER PRIMARY KEY,
                schema_name TEXT NOT NULL,
                version INTEGER NOT NULL,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
                note TEXT,
                UNIQUE(schema_name, version)
            );
            """
        )
        conn.executescript(_OLD_TRACK_IDENTITY_SQL)
        conn.execute(
            "INSERT INTO schema_migrations (schema_name, version, note) VALUES ('v3', 15, 'fixture')"
        )

        applied = run_pending_v3(conn)

        assert "0016_tidal_audio_fields.sql" in applied
        assert "0017_spotify_intake_ingestion_method.py" in applied

        conn.execute(
            """
            INSERT INTO track_identity (
                identity_key,
                spotify_id,
                ingested_at,
                ingestion_method,
                ingestion_source,
                ingestion_confidence
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "spotify:abc123",
                "abc123",
                "2026-04-03T00:00:00+00:00",
                "spotify_intake",
                "spotiflac:https://open.spotify.com/track/abc123|service:qobuz",
                "high",
            ),
        )
    finally:
        conn.close()
