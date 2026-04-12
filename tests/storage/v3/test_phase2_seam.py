import sqlite3

from tagslut.storage.v3 import create_schema_v3
from tagslut.storage.v3 import classify_ingestion_track, dual_write_registered_file


def _open_in_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)
    return conn


def test_track_a_provider_api_single_isrc() -> None:
    method, confidence = classify_ingestion_track(
        isrc="GBUM71505512",
        beatport_id=None,
        tidal_id="123",
        spotify_id=None,
        qobuz_id=None,
        download_source="tidal",
    )
    assert method == "provider_api"
    assert confidence == "high"


def test_track_a_provider_api_no_isrc() -> None:
    method, confidence = classify_ingestion_track(
        isrc=None,
        beatport_id=None,
        tidal_id="123",
        spotify_id=None,
        qobuz_id=None,
        download_source="tidal",
    )
    assert method == "provider_api"
    assert confidence == "uncertain"


def test_track_b_corroborated() -> None:
    method, confidence = classify_ingestion_track(
        isrc="GBUM71505512",
        beatport_id="999",
        tidal_id="123",
        spotify_id=None,
        qobuz_id=None,
        download_source="unknown",
    )
    assert method == "multi_provider_reconcile"
    assert confidence == "corroborated"


def test_track_b_high_single_provider() -> None:
    method, confidence = classify_ingestion_track(
        isrc="GBUM71505512",
        beatport_id="999",
        tidal_id=None,
        spotify_id=None,
        qobuz_id=None,
        download_source="unknown",
    )
    assert method == "multi_provider_reconcile"
    assert confidence == "high"


def test_track_b_uncertain_no_isrc() -> None:
    method, confidence = classify_ingestion_track(
        isrc=None,
        beatport_id="999",
        tidal_id="123",
        spotify_id=None,
        qobuz_id=None,
        download_source="unknown",
    )
    assert method == "multi_provider_reconcile"
    assert confidence == "uncertain"


def test_fallback_to_migration() -> None:
    method, confidence = classify_ingestion_track(
        isrc=None,
        beatport_id=None,
        tidal_id=None,
        spotify_id=None,
        qobuz_id=None,
        download_source=None,
    )
    assert method == "migration"
    assert confidence == "legacy"


def test_dual_write_uses_classify() -> None:
    conn = _open_in_memory_db()
    asset_id, identity_id = dual_write_registered_file(
        conn,
        path="/tmp/test.flac",
        content_sha256=None,
        streaminfo_md5=None,
        checksum=None,
        size_bytes=1,
        mtime=0.0,
        duration_s=1.0,
        sample_rate=44100,
        bit_depth=16,
        bitrate=320,
        library=None,
        zone=None,
        download_source="tidal",
        download_date=None,
        mgmt_status="registered",
        metadata={
            "isrc": "GBUM71505512",
            "tidal_id": "123",
            "artist": "Artist",
            "title": "Title",
        },
        duration_ref_ms=None,
        duration_ref_source=None,
    )
    assert asset_id is not None
    assert identity_id is not None
    row = conn.execute(
        "SELECT ingestion_method, ingestion_confidence FROM track_identity WHERE id = ?",
        (int(identity_id),),
    ).fetchone()
    assert row is not None
    assert row["ingestion_method"] == "provider_api"
    assert row["ingestion_confidence"] == "high"

