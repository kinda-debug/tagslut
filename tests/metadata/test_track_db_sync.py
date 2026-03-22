from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tagslut.metadata.track_db_sync import sync_v3_from_track_db


def _create_work_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            dj_pool_path TEXT,
            canonical_title TEXT,
            canonical_artist TEXT,
            canonical_album TEXT,
            canonical_genre TEXT,
            canonical_bpm REAL,
            canonical_key TEXT,
            canonical_label TEXT,
            enrichment_providers TEXT,
            enriched_at TEXT
        );
        CREATE TABLE asset_file (
            id INTEGER PRIMARY KEY,
            path TEXT NOT NULL
        );
        CREATE TABLE asset_link (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER NOT NULL,
            identity_id INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE track_identity (
            id INTEGER PRIMARY KEY,
            canonical_title TEXT,
            canonical_artist TEXT,
            canonical_album TEXT,
            canonical_genre TEXT,
            canonical_bpm REAL,
            canonical_key TEXT,
            canonical_label TEXT,
            enriched_at TEXT,
            updated_at TEXT,
            ingested_at TEXT,
            ingestion_method TEXT,
            ingestion_source TEXT,
            ingestion_confidence TEXT,
            merged_into_id INTEGER
        );
        """
    )
    return conn


def _create_donor_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE Track (
            id INTEGER PRIMARY KEY,
            location TEXT NOT NULL,
            title TEXT,
            artist TEXT,
            albumTitle TEXT,
            genre TEXT NOT NULL,
            bpm REAL NOT NULL,
            key TEXT NOT NULL,
            label TEXT NOT NULL
        );
        """
    )
    return conn


def test_sync_updates_files_and_identity_by_dj_pool_path(tmp_path: Path) -> None:
    work_conn = _create_work_db(tmp_path / "work.db")
    donor_conn = _create_donor_db(tmp_path / "donor.db")
    try:
        work_conn.execute(
            """
            INSERT INTO files (
                path, dj_pool_path, canonical_title, canonical_artist, canonical_album,
                canonical_genre, canonical_bpm, canonical_key, canonical_label,
                enrichment_providers, enriched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/music/source.flac",
                "/Volumes/MUSIC/DJ_LIBRARY/Artist/Track.mp3",
                None,
                None,
                None,
                None,
                120.0,
                None,
                None,
                json.dumps(["tidal"]),
                None,
            ),
        )
        work_conn.execute("INSERT INTO asset_file (id, path) VALUES (1, ?)", ("/music/source.flac",))
        work_conn.execute("INSERT INTO asset_link (asset_id, identity_id, active) VALUES (1, 10, 1)")
        work_conn.execute(
            """
            INSERT INTO track_identity (
                id, canonical_title, canonical_artist, canonical_album,
                canonical_genre, canonical_bpm, canonical_key, canonical_label,
                enriched_at, updated_at,
                ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (10, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None, None, None, None, 120.0, None, None, None, None,
                "2026-01-01T00:00:00+00:00", "migration", "test_fixture", "legacy",
            ),
        )

        donor_conn.execute(
            "INSERT INTO Track (location, title, artist, albumTitle, genre, bpm, key, label) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "/Volumes/MUSIC/DJ_LIBRARY/Artist/Track.mp3",
                "Track",
                "Artist",
                "Album",
                "Indie Dance",
                123.0,
                "Em",
                "Life and Death",
            ),
        )
        donor_conn.commit()

        result = sync_v3_from_track_db(work_conn, donor_conn, execute=True)
        work_conn.commit()

        assert result.matched_files == 1
        assert result.file_rows_updated == 1
        assert result.identity_rows_updated == 1

        file_row = work_conn.execute(
            """
            SELECT canonical_genre, canonical_bpm, canonical_key, canonical_label, enrichment_providers, enriched_at
            FROM files
            WHERE path = '/music/source.flac'
            """
        ).fetchone()
        assert tuple(file_row) == (
            "Indie Dance",
            120.0,
            "Em",
            "Life and Death",
            json.dumps(["tidal", "rekordbox_main_db"]),
            file_row[5],
        )
        assert file_row[5] is not None

        identity_row = work_conn.execute(
            """
            SELECT canonical_genre, canonical_bpm, canonical_key, canonical_label, enriched_at, updated_at
            FROM track_identity
            WHERE id = 10
            """
        ).fetchone()
        assert tuple(identity_row[0:4]) == ("Indie Dance", 120.0, "Em", "Life and Death")
        assert identity_row[4] is not None
        assert identity_row[5] is not None
    finally:
        work_conn.close()
        donor_conn.close()


def test_sync_skips_conflicting_identity_fields(tmp_path: Path) -> None:
    work_conn = _create_work_db(tmp_path / "work.db")
    donor_conn = _create_donor_db(tmp_path / "donor.db")
    try:
        work_conn.executemany(
            """
            INSERT INTO files (
                path, dj_pool_path, canonical_title, canonical_artist, canonical_album,
                canonical_genre, canonical_bpm, canonical_key, canonical_label,
                enrichment_providers, enriched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("/music/a.flac", "/Volumes/MUSIC/DJ_LIBRARY/A.mp3", None, None, None, None, None, None, None, None, None),
                ("/music/b.flac", "/Volumes/MUSIC/DJ_LIBRARY/B.mp3", None, None, None, None, None, None, None, None, None),
            ],
        )
        work_conn.executemany(
            "INSERT INTO asset_file (id, path) VALUES (?, ?)",
            [(1, "/music/a.flac"), (2, "/music/b.flac")],
        )
        work_conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            [(1, 20), (2, 20)],
        )
        work_conn.execute(
            """
            INSERT INTO track_identity (
                id, canonical_title, canonical_artist, canonical_album,
                canonical_genre, canonical_bpm, canonical_key, canonical_label,
                enriched_at, updated_at,
                ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (20, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None, None, None, None, None, None, None, None, None,
                "2026-01-01T00:00:00+00:00", "migration", "test_fixture", "legacy",
            ),
        )

        donor_conn.executemany(
            "INSERT INTO Track (location, title, artist, albumTitle, genre, bpm, key, label) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("/Volumes/MUSIC/DJ_LIBRARY/A.mp3", "A", "Artist A", "Album A", "House", 124.0, "Gm", "Label A"),
                ("/Volumes/MUSIC/DJ_LIBRARY/B.mp3", "B", "Artist B", "Album B", "House", 124.0, "Gm", "Label B"),
            ],
        )
        donor_conn.commit()

        result = sync_v3_from_track_db(work_conn, donor_conn, execute=True)
        work_conn.commit()

        assert result.file_rows_updated == 2
        assert result.identity_rows_updated == 1
        assert result.identity_field_conflicts["label"] == 1

        identity_row = work_conn.execute(
            "SELECT canonical_genre, canonical_bpm, canonical_key, canonical_label FROM track_identity WHERE id = 20"
        ).fetchone()
        assert tuple(identity_row) == ("House", 124.0, "Gm", None)
    finally:
        work_conn.close()
        donor_conn.close()


def test_sync_updates_by_normalized_title_artist_album_with_field_consensus(tmp_path: Path) -> None:
    work_conn = _create_work_db(tmp_path / "work.db")
    donor_conn = _create_donor_db(tmp_path / "donor.db")
    try:
        work_conn.execute(
            """
            INSERT INTO files (
                path, dj_pool_path, canonical_title, canonical_artist, canonical_album,
                canonical_genre, canonical_bpm, canonical_key, canonical_label,
                enrichment_providers, enriched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/music/source.flac",
                "/Volumes/MUSIC/DJ_LIBRARY/non-matching-path.mp3",
                "Anywhere",
                "Ratboys",
                "The Window",
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        )
        work_conn.execute("INSERT INTO asset_file (id, path) VALUES (1, ?)", ("/music/source.flac",))
        work_conn.execute("INSERT INTO asset_link (asset_id, identity_id, active) VALUES (1, 30, 1)")
        work_conn.execute(
            """
            INSERT INTO track_identity (
                id, canonical_title, canonical_artist, canonical_album,
                canonical_genre, canonical_bpm, canonical_key, canonical_label,
                enriched_at, updated_at,
                ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (30, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Anywhere", "Ratboys", "The Window", None, None, None, None, None, None,
                "2026-01-01T00:00:00+00:00", "migration", "test_fixture", "legacy",
            ),
        )

        donor_conn.executemany(
            "INSERT INTO Track (location, title, artist, albumTitle, genre, bpm, key, label) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "/Volumes/MUSIC/DJ_LIBRARY/Anywhere-1.mp3",
                    "Anywhere",
                    "Ratboys",
                    "The Window",
                    "Indie Rock",
                    120.0,
                    "Am",
                    "Top Shelf",
                ),
                (
                    "/Volumes/MUSIC/DJ_LIBRARY/Anywhere-2.mp3",
                    "Anywhere",
                    "Ratboys",
                    "The Window",
                    "Indie Rock",
                    120.0,
                    "Am",
                    "Different Label",
                ),
            ],
        )
        donor_conn.commit()

        result = sync_v3_from_track_db(work_conn, donor_conn, match_mode="normalized_taa", execute=True)
        work_conn.commit()

        assert result.matched_files == 1
        assert result.match_mode_counts["normalized_taa"] == 1
        assert result.file_field_conflicts["label"] == 1
        assert result.identity_field_conflicts["label"] == 0

        file_row = work_conn.execute(
            "SELECT canonical_genre, canonical_bpm, canonical_key, canonical_label FROM files WHERE path = '/music/source.flac'"
        ).fetchone()
        assert tuple(file_row) == ("Indie Rock", 120.0, "Am", None)

        identity_row = work_conn.execute(
            "SELECT canonical_genre, canonical_bpm, canonical_key, canonical_label FROM track_identity WHERE id = 30"
        ).fetchone()
        assert tuple(identity_row) == ("Indie Rock", 120.0, "Am", None)
    finally:
        work_conn.close()
        donor_conn.close()
