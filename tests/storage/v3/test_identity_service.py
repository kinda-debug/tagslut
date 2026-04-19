from __future__ import annotations

import sqlite3

import pytest

from tagslut.storage.schema import init_db
from tagslut.storage.v3.identity_service import (
    link_asset_to_identity,
    mirror_identity_to_legacy,
    resolve_active_identity,
    resolve_or_create_identity,
)
from tagslut.storage.v3.schema import create_schema_v3


def _setup_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)
    init_db(conn)
    return conn


def test_exact_reuse_by_isrc() -> None:
    conn = _setup_db()
    try:
        conn.execute(
            "INSERT INTO track_identity (id, identity_key, isrc, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (1, 'isrc:abc123', 'ABC123', '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')"
        )
        identity_id = resolve_or_create_identity(
            conn,
            asset_row={"path": "/music/new.flac", "duration_s": 300.0},
            metadata={"isrc": "ABC123", "artist": "Artist", "title": "Track"},
            provenance={"source": "tidal"},
        )
        assert identity_id == 1
    finally:
        conn.close()


def test_exact_reuse_by_provider_id() -> None:
    conn = _setup_db()
    try:
        conn.execute(
            """
            INSERT INTO track_identity (id, identity_key, beatport_id, canonical_artist, canonical_title, ingested_at, ingestion_method, ingestion_source, ingestion_confidence)
            VALUES (2, 'beatport_id:12345', '12345', 'Artist', 'Track', '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')
            """
        )
        identity_id = resolve_or_create_identity(
            conn,
            asset_row={"path": "/music/provider.flac", "duration_s": 300.0},
            metadata={"beatport_id": "12345", "artist": "Artist", "title": "Track"},
            provenance={"source": "beatport"},
        )
        assert identity_id == 2
    finally:
        conn.close()


def test_exact_reuse_by_spotify_id() -> None:
    conn = _setup_db()
    try:
        conn.execute(
            """
            INSERT INTO track_identity (id, identity_key, spotify_id, canonical_artist, canonical_title, ingested_at, ingestion_method, ingestion_source, ingestion_confidence)
            VALUES (12, 'spotify:sp-1', 'sp-1', 'Artist', 'Track', '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')
            """
        )
        identity_id = resolve_or_create_identity(
            conn,
            asset_row={"path": "/music/provider-spotify.flac"},
            metadata={"spotify_id": "sp-1", "artist": "Artist", "title": "Track"},
            provenance={"source": "spotify"},
        )
        assert identity_id == 12
    finally:
        conn.close()


def test_text_match_records_candidate_then_creates_when_no_strong_match() -> None:
    conn = _setup_db()
    try:
        conn.execute(
            """
            INSERT INTO track_identity (
                id, identity_key, artist_norm, title_norm, canonical_artist, canonical_title, duration_ref_ms,
                ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (3, 'text:artist|track', 'artist', 'track', 'Artist', 'Track', 300000,
                '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')
            """
        )
        created_from_text = resolve_or_create_identity(
            conn,
            asset_row={"path": "/music/fuzzy.flac", "duration_s": 299.5},
            metadata={"artist": "Artist", "title": "Track"},
            provenance={"source": "manual"},
        )
        created = resolve_or_create_identity(
            conn,
            asset_row={"path": "/music/new-create.flac", "duration_s": 420.0},
            metadata={"artist": "Other Artist", "title": "Other Track"},
            provenance={"source": "manual"},
        )

        assert created_from_text != 3
        assert created != 3
        candidate = conn.execute(
            """
            SELECT irc.identity_id, irc.match_method, irc.decision
            FROM identity_resolution_candidate irc
            JOIN identity_resolution_run irr ON irr.id = irc.run_id
            WHERE irr.source_ref = '/music/fuzzy.flac'
            """
        ).fetchone()
        assert candidate is not None
        assert int(candidate["identity_id"]) == 3
        assert candidate["match_method"] in {"exact_text", "fuzzy_text"}
        assert candidate["decision"] == "candidate"
        row = conn.execute("SELECT identity_key FROM track_identity WHERE id = ?", (created,)).fetchone()
        assert row is not None
        assert str(row["identity_key"]).startswith("unresolved_text:path:/music/new-create.flac")
    finally:
        conn.close()


def test_resolve_active_identity_follows_single_merge_hop() -> None:
    conn = _setup_db()
    try:
        conn.executemany(
            "INSERT INTO track_identity (id, identity_key, merged_into_id, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (10, "id:active", None, "2026-01-01T00:00:00+00:00", "migration", "test_fixture", "legacy"),
                (11, "id:merged", 10, "2026-01-01T00:00:00+00:00", "migration", "test_fixture", "legacy"),
            ],
        )
        row = resolve_active_identity(conn, 11)
        assert int(row["id"]) == 10
        assert str(row["identity_key"]) == "id:active"
    finally:
        conn.close()


def test_resolve_active_identity_rejects_transitive_merge_chain() -> None:
    conn = _setup_db()
    try:
        conn.executemany(
            "INSERT INTO track_identity (id, identity_key, merged_into_id, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (20, "id:active", None, "2026-01-01T00:00:00+00:00", "migration", "test_fixture", "legacy"),
                (21, "id:merged", 20, "2026-01-01T00:00:00+00:00", "migration", "test_fixture", "legacy"),
                (22, "id:transitive", 21, "2026-01-01T00:00:00+00:00", "migration", "test_fixture", "legacy"),
            ],
        )
        with pytest.raises(RuntimeError, match="transitive"):
            resolve_active_identity(conn, 22)
    finally:
        conn.close()


def test_resolve_or_create_identity_mirrors_legacy_on_create() -> None:
    conn = _setup_db()
    try:
        conn.execute("INSERT INTO asset_file (id, path, duration_s) VALUES (9, '/music/auto.flac', 300.0)")
        conn.execute("INSERT INTO files (path, library_track_key) VALUES ('/music/auto.flac', NULL)")

        identity_id = resolve_or_create_identity(
            conn,
            asset_row={"id": 9, "path": "/music/auto.flac", "duration_s": 300.0},
            metadata={"isrc": "US1234567890", "artist": "Artist", "title": "Track", "beatport_id": "1"},
            provenance={"source": "beatport"},
        )

        row = conn.execute(
            "SELECT identity_key FROM track_identity WHERE id = ?",
            (identity_id,),
        ).fetchone()
        assert row is not None
        identity_key = str(row["identity_key"])

        file_row = conn.execute(
            "SELECT library_track_key, canonical_artist, canonical_title, beatport_id FROM files WHERE path = ?",
            ("/music/auto.flac",),
        ).fetchone()
        assert file_row is not None
        assert file_row["library_track_key"] == identity_key
        assert file_row["canonical_artist"] == "Artist"
        assert file_row["canonical_title"] == "Track"
        assert file_row["beatport_id"] == "1"

        track_row = conn.execute(
            "SELECT library_track_key, artist, title, isrc FROM library_tracks WHERE library_track_key = ?",
            (identity_key,),
        ).fetchone()
        assert track_row is not None
        assert track_row["library_track_key"] == identity_key
        assert track_row["artist"] == "Artist"
        assert track_row["title"] == "Track"
        assert track_row["isrc"] == "US1234567890"
    finally:
        conn.close()


def test_phase1_rename_backfills_canonical_columns() -> None:
    conn = _setup_db()
    try:
        conn.execute("ALTER TABLE track_identity ADD COLUMN label TEXT")
        conn.execute("ALTER TABLE track_identity ADD COLUMN catalog_number TEXT")
        conn.execute("ALTER TABLE track_identity ADD COLUMN canonical_duration_s REAL")
        conn.execute(
            """
            INSERT INTO track_identity (
                id, identity_key, isrc, label, catalog_number, canonical_duration_s,
                ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (
                33, 'isrc:legacy-1', 'LEGACY1', 'LegacyLabel', 'CAT-1', 123.0,
                '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'
            )
            """
        )
        identity_id = resolve_or_create_identity(
            conn,
            asset_row={"path": "/music/legacy.flac"},
            metadata={"isrc": "legacy1", "artist": "Artist", "title": "Track"},
            provenance={"source": "manual"},
        )
        assert identity_id == 33
        row = conn.execute(
            "SELECT canonical_label, canonical_catalog_number, canonical_duration FROM track_identity WHERE id = ?",
            (33,),
        ).fetchone()
        assert row is not None
        assert row["canonical_label"] == "LegacyLabel"
        assert row["canonical_catalog_number"] == "CAT-1"
        assert float(row["canonical_duration"]) == 123.0
    finally:
        conn.close()


def test_legacy_mirror_updates_files_and_library_tracks() -> None:
    conn = _setup_db()
    try:
        conn.execute("INSERT INTO asset_file (id, path) VALUES (5, '/music/a.flac')")
        conn.execute(
            "INSERT INTO files (path, library_track_key) VALUES ('/music/a.flac', NULL)"
        )
        conn.execute(
            """
            INSERT INTO track_identity (
                id, identity_key, isrc, beatport_id, canonical_artist, canonical_title,
                canonical_album, canonical_genre, canonical_bpm, canonical_key,
                canonical_label, canonical_release_date, duration_ref_ms,
                ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (
                7, 'isrc:abc123', 'ABC123', '999', 'Artist', 'Track',
                'Album', 'House', 124.0, 'Am', 'Label', '2024-01-01', 301000,
                '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'
            )
            """
        )
        link_asset_to_identity(conn, asset_id=5, identity_id=7, confidence=1.0, link_source="test")
        mirror_identity_to_legacy(conn, identity_id=7, asset_id=5)

        file_row = conn.execute(
            "SELECT library_track_key, canonical_artist, canonical_title, beatport_id FROM files WHERE path = ?",
            ("/music/a.flac",),
        ).fetchone()
        track_row = conn.execute(
            "SELECT library_track_key, artist, title, isrc, bpm FROM library_tracks WHERE library_track_key = ?",
            ("isrc:abc123",),
        ).fetchone()

        assert file_row is not None
        assert file_row["library_track_key"] == "isrc:abc123"
        assert file_row["canonical_artist"] == "Artist"
        assert file_row["canonical_title"] == "Track"
        assert file_row["beatport_id"] == "999"

        assert track_row is not None
        assert track_row["library_track_key"] == "isrc:abc123"
        assert track_row["artist"] == "Artist"
        assert track_row["title"] == "Track"
        assert track_row["isrc"] == "ABC123"
        assert float(track_row["bpm"]) == 124.0
    finally:
        conn.close()
