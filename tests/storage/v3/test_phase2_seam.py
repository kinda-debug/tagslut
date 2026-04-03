from __future__ import annotations

import sqlite3

from tagslut.storage.schema import init_db
from tagslut.storage.v3.dual_write import classify_ingestion_track, dual_write_registered_file
from tagslut.storage.v3.schema import create_schema_v3


def _setup_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)
    init_db(conn)
    return conn


def test_track_a_provider_api_single_isrc() -> None:
    assert classify_ingestion_track(
        isrc="US1234567890",
        beatport_id=None,
        tidal_id=None,
        spotify_id=None,
        qobuz_id=None,
        download_source="tidal",
    ) == ("provider_api", "high")


def test_track_a_provider_api_no_isrc() -> None:
    assert classify_ingestion_track(
        isrc=None,
        beatport_id=None,
        tidal_id=None,
        spotify_id=None,
        qobuz_id=None,
        download_source="tidal",
    ) == ("provider_api", "uncertain")


def test_track_b_corroborated() -> None:
    assert classify_ingestion_track(
        isrc="US1234567890",
        beatport_id="123",
        tidal_id="456",
        spotify_id=None,
        qobuz_id=None,
        download_source="manual",
    ) == ("multi_provider_reconcile", "corroborated")


def test_track_b_high_single_provider() -> None:
    assert classify_ingestion_track(
        isrc="US1234567890",
        beatport_id="123",
        tidal_id=None,
        spotify_id=None,
        qobuz_id=None,
        download_source="manual",
    ) == ("multi_provider_reconcile", "high")


def test_track_b_uncertain_no_isrc() -> None:
    assert classify_ingestion_track(
        isrc=None,
        beatport_id="123",
        tidal_id="456",
        spotify_id=None,
        qobuz_id=None,
        download_source="manual",
    ) == ("multi_provider_reconcile", "uncertain")


def test_fallback_to_migration() -> None:
    assert classify_ingestion_track(
        isrc=None,
        beatport_id=None,
        tidal_id=None,
        spotify_id=None,
        qobuz_id=None,
        download_source=None,
    ) == ("migration", "legacy")


def test_spotiflac_download_source_classifies_as_spotify_intake() -> None:
    assert classify_ingestion_track(
        isrc="US1234567890",
        beatport_id=None,
        tidal_id=None,
        spotify_id="spotify-123",
        qobuz_id="qobuz-456",
        download_source="spotiflac_qobuz",
    ) == ("spotify_intake", "high")


def test_dual_write_uses_classify() -> None:
    conn = _setup_db()
    try:
        _, identity_id = dual_write_registered_file(
            conn,
            path="/music/test.flac",
            content_sha256="abc123",
            streaminfo_md5="def456",
            checksum="abc123",
            size_bytes=1234,
            mtime=100.0,
            duration_s=300.0,
            sample_rate=44100,
            bit_depth=16,
            bitrate=900,
            library="default",
            zone="staging",
            download_source="tidal",
            download_date="2026-03-22T00:00:00Z",
            mgmt_status="new",
            metadata={"ISRC": "US1234567890", "artist": "Example", "title": "Track"},
            duration_ref_ms=300000,
            duration_ref_source="tidal",
            event_time="2026-03-22T00:00:00Z",
        )

        row = conn.execute(
            "SELECT ingestion_method, ingestion_confidence FROM track_identity WHERE id = ?",
            (identity_id,),
        ).fetchone()

        assert row is not None
        assert row["ingestion_method"] == "provider_api"
        assert row["ingestion_confidence"] == "high"
    finally:
        conn.close()


def test_dual_write_accepts_spotify_overrides() -> None:
    conn = _setup_db()
    try:
        _, identity_id = dual_write_registered_file(
            conn,
            path="/music/spotify.flac",
            content_sha256="sha",
            streaminfo_md5="md5",
            checksum="sha",
            size_bytes=1234,
            mtime=100.0,
            duration_s=300.0,
            sample_rate=44100,
            bit_depth=16,
            bitrate=900,
            library="default",
            zone="accepted",
            download_source="tidal",
            download_date="2026-04-03T00:00:00Z",
            mgmt_status="promoted_to_final_library",
            metadata={"artist": "Example", "title": "Track", "isrc": "US1234567890"},
            duration_ref_ms=300000,
            duration_ref_source="spotify",
            download_source_override="spotiflac_qobuz",
            ingestion_method_override="spotify_intake",
            ingestion_source_override="spotiflac:https://open.spotify.com/track/abc|service:qobuz",
            ingestion_confidence_override="high",
            provider_id_hints={"spotify_id": "abc", "qobuz_id": "qbz123"},
        )

        row = conn.execute(
            """
            SELECT ingestion_method, ingestion_source, ingestion_confidence, spotify_id, qobuz_id
            FROM track_identity
            WHERE id = ?
            """,
            (identity_id,),
        ).fetchone()

        assert row is not None
        assert row["ingestion_method"] == "spotify_intake"
        assert row["ingestion_source"] == "spotiflac:https://open.spotify.com/track/abc|service:qobuz"
        assert row["ingestion_confidence"] == "high"
        assert row["spotify_id"] == "abc"
        assert row["qobuz_id"] == "qbz123"
    finally:
        conn.close()
