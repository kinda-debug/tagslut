from __future__ import annotations

import sqlite3

from tagslut.intake.spotify import SpotifyTrack
from tagslut.storage.schema import init_db
from tagslut.storage.v3.backfill_spotify_ids import _select_rows, choose_spotify_candidate
from tagslut.storage.v3.identity_service import link_asset_to_identity, merge_identity_fields_if_empty
from tagslut.storage.v3.schema import create_schema_v3


def _setup_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)
    init_db(conn)
    return conn


def _spotify_track(*, spotify_id: str, isrc: str, artist: str, title: str) -> SpotifyTrack:
    return SpotifyTrack(
        spotify_id=spotify_id,
        spotify_url=f"https://open.spotify.com/track/{spotify_id}",
        title=title,
        artist=artist,
        album="",
        album_artist=artist,
        release_date="",
        duration_ms=None,
        isrc=isrc,
        track_number=1,
        total_tracks=1,
        disc_number=1,
        total_discs=1,
        cover_url="",
        copyright="",
        publisher="",
        collection_type="search",
        collection_title="",
        playlist_index=1,
    )


def test_choose_spotify_candidate_uses_artist_title_tiebreak() -> None:
    row = {
        "isrc": "ABC123",
        "artist_norm": "artist a",
        "title_norm": "track a",
        "canonical_artist": "Artist A",
        "canonical_title": "Track A",
        "duration_ref_ms": None,
    }
    hits = [
        _spotify_track(spotify_id="sp-1", isrc="ABC123", artist="Artist A", title="Track A"),
        _spotify_track(spotify_id="sp-2", isrc="ABC123", artist="Other Artist", title="Other Track"),
    ]

    selection = choose_spotify_candidate(row, hits)

    assert selection.spotify_id == "sp-1"
    assert selection.reason == "artist_title_tiebreak"
    assert selection.details
    assert selection.details[0].spotify_id == "sp-1"


def test_choose_spotify_candidate_exposes_ambiguous_candidates() -> None:
    row = {
        "isrc": "ABC123",
        "artist_norm": "artist a",
        "title_norm": "track a",
        "canonical_artist": "Artist A",
        "canonical_title": "Track A",
        "duration_ref_ms": None,
    }
    hits = [
        _spotify_track(spotify_id="sp-1", isrc="ABC123", artist="Artist A", title="Track A"),
        _spotify_track(spotify_id="sp-2", isrc="ABC123", artist="Artist A", title="Track A"),
    ]
    hits[0].duration_ms = 180000
    hits[1].duration_ms = 181000

    selection = choose_spotify_candidate(row, hits)

    assert selection.spotify_id is None
    assert selection.reason == "ambiguous"
    assert len(selection.details) == 2
    assert selection.details[0].spotify_id == "sp-1"


def test_choose_spotify_candidate_normalizes_title_artist_and_breaks_semantic_ties() -> None:
    row = {
        "isrc": "FR96X2595969",
        "artist_norm": "helsloot, booka shade",
        "title_norm": "broken glass (helsloot extended remix)",
        "canonical_artist": "Helsloot, Booka Shade",
        "canonical_title": "Broken Glass (Helsloot Extended Remix)",
        "duration_ref_ms": 467000,
    }
    hits = [
        _spotify_track(
            spotify_id="late-release",
            isrc="FR96X2595969",
            artist="Booka Shade, Helsloot",
            title="Broken Glass - Helsloot Extended Remix",
        ),
        _spotify_track(
            spotify_id="early-release",
            isrc="FR96X2595969",
            artist="Booka Shade, Helsloot",
            title="Broken Glass - Helsloot Extended Remix",
        ),
    ]
    hits[0].album = "For Real Album Remixes"
    hits[0].release_date = "2025-05-30"
    hits[0].duration_ms = 467000
    hits[1].album = "Broken Glass (Helsloot Remix)"
    hits[1].release_date = "2025-05-09"
    hits[1].duration_ms = 467000

    selection = choose_spotify_candidate(row, hits)

    assert selection.spotify_id == "early-release"
    assert selection.reason == "semantic_tie_break"


def test_choose_spotify_candidate_accepts_artist_subset_when_title_and_duration_match() -> None:
    row = {
        "isrc": "FRX202578683",
        "artist_norm": "booka shade, joplyn",
        "title_norm": "right now (p.i.n. 4) (chris luno extended remix)",
        "canonical_artist": "",
        "canonical_title": "",
        "duration_ref_ms": 358000,
    }
    hits = [
        _spotify_track(
            spotify_id="release-a",
            isrc="FRX202578683",
            artist="Booka Shade, JOPLYN, Chris Luno",
            title="Right Now (P.I.N. 4) - Chris Luno Extended Remix",
        ),
        _spotify_track(
            spotify_id="release-b",
            isrc="FRX202578683",
            artist="Booka Shade, JOPLYN, Chris Luno",
            title="Right Now (P.I.N. 4) - Chris Luno Extended Remix",
        ),
    ]
    hits[0].album = "For Real The Complete Remix Collection"
    hits[0].release_date = "2026-03-20"
    hits[0].duration_ms = 358000
    hits[1].album = "For Real Album Remixes"
    hits[1].release_date = "2025-05-30"
    hits[1].duration_ms = 358000

    selection = choose_spotify_candidate(row, hits)

    assert selection.spotify_id == "release-b"
    assert selection.reason == "semantic_tie_break"


def test_merge_identity_fields_if_empty_mirrors_spotify_id_to_files() -> None:
    conn = _setup_db()
    try:
        conn.execute("INSERT INTO asset_file (id, path) VALUES (5, '/music/a.flac')")
        conn.execute("INSERT INTO files (path, library_track_key, spotify_id) VALUES ('/music/a.flac', NULL, NULL)")
        conn.execute(
            """
            INSERT INTO track_identity (
                id, identity_key, isrc, canonical_artist, canonical_title,
                ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (
                7, 'isrc:abc123', 'ABC123', 'Artist', 'Track',
                '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'
            )
            """
        )
        link_asset_to_identity(conn, asset_id=5, identity_id=7, confidence=1.0, link_source="test")

        merge_identity_fields_if_empty(
            conn,
            7,
            {"isrc": "ABC123", "spotify_id": "sp-123"},
            {"ingestion_method": "isrc_lookup", "ingestion_source": "spotify_api:isrc=ABC123"},
            asset_id=5,
        )

        identity_row = conn.execute(
            "SELECT spotify_id FROM track_identity WHERE id = 7"
        ).fetchone()
        file_row = conn.execute(
            "SELECT spotify_id FROM files WHERE path = '/music/a.flac'"
        ).fetchone()
        assert identity_row is not None
        assert file_row is not None
        assert identity_row["spotify_id"] == "sp-123"
        assert file_row["spotify_id"] == "sp-123"
    finally:
        conn.close()


def test_select_rows_supports_priority_filters() -> None:
    conn = _setup_db()
    try:
        conn.executemany(
            """
            INSERT INTO track_identity (
                id, identity_key, isrc, canonical_artist, canonical_title, artist_norm, title_norm,
                ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?,
                '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')
            """,
            [
                (1, "isrc:a", "ISRC-A", "Booka Shade", "Broken Glass", "booka shade", "broken glass"),
                (2, "isrc:b", "ISRC-B", "VIMES", "Celestial", "vimes", "celestial"),
                (3, "isrc:c", "ISRC-C", "Luces", "Who's to Say", "luces", "who s to say"),
            ],
        )

        artist_rows = _select_rows(conn, resume_from_id=0, limit=None, artist_terms=("booka",))
        title_rows = _select_rows(conn, resume_from_id=0, limit=None, title_terms=("celestial",))
        isrc_rows = _select_rows(conn, resume_from_id=0, limit=None, isrc_terms=("ISRC-C",))
        newest_rows = _select_rows(conn, resume_from_id=0, limit=None)
        resumed_rows = _select_rows(conn, resume_from_id=2, limit=None)

        assert [int(row["id"]) for row in artist_rows] == [1]
        assert [int(row["id"]) for row in title_rows] == [2]
        assert [int(row["id"]) for row in isrc_rows] == [3]
        assert [int(row["id"]) for row in newest_rows] == [3, 2, 1]
        assert [int(row["id"]) for row in resumed_rows] == [1]
    finally:
        conn.close()
