import sqlite3
from pathlib import Path

from tagslut.metadata.models.types import EnrichmentResult, MatchConfidence, ProviderTrack
from tagslut.metadata.store.db_writer import update_database
from tagslut.storage.schema import init_db
from tagslut.storage.v3.migration_runner import run_pending_v3
from tagslut.storage.v3.schema import create_schema_v3


def test_update_database_writes_provider_ids_in_recovery_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        conn.execute("INSERT INTO files (path) VALUES (?)", ("/music/test.flac",))
        conn.commit()
    finally:
        conn.close()

    result = EnrichmentResult(
        path="/music/test.flac",
        beatport_id="123",
        tidal_id="456",
    )

    ok = update_database(db_path=db_path, result=result, dry_run=False, mode="recovery")
    assert ok is True

    check_conn = sqlite3.connect(db_path)
    try:
        row = check_conn.execute(
            "SELECT beatport_id, tidal_id FROM files WHERE path = ?",
            ("/music/test.flac",),
        ).fetchone()
    finally:
        check_conn.close()

    assert row is not None
    assert row[0] == "123"
    assert row[1] == "456"


def test_update_database_persists_tidal_native_fields_to_v3_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "test_v2_v3.db"
    conn = sqlite3.connect(db_path)
    try:
        create_schema_v3(conn)
        init_db(conn)
        run_pending_v3(conn)

        conn.execute("INSERT INTO files (path) VALUES (?)", ("/music/test.flac",))

        conn.execute("INSERT INTO asset_file (id, path) VALUES (?, ?)", (1, "/music/test.flac"))
        conn.execute(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                ingested_at,
                ingestion_method,
                ingestion_source,
                ingestion_confidence,
                tidal_bpm,
                tidal_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                10,
                "id:10",
                "2026-01-01T00:00:00Z",
                "manual",
                "fixture",
                "legacy",
                120.0,
                "C",
            ),
        )
        conn.execute(
            """
            INSERT INTO asset_link (asset_id, identity_id, confidence, link_source, active)
            VALUES (?, ?, ?, ?, ?)
            """,
            (1, 10, 1.0, "fixture", 1),
        )
        conn.commit()
    finally:
        conn.close()

    tidal_match = ProviderTrack(
        service="tidal",
        service_track_id="123",
        title="Test Track",
        artist="Test Artist",
        match_confidence=MatchConfidence.EXACT,
        tidal_bpm=128.0,
        tidal_key="FSharp",
        tidal_key_scale="MINOR",
        tidal_camelot="11A",
        replay_gain_track=-8.0,
        replay_gain_album=-7.5,
        tidal_dj_ready=1,
        tidal_stem_ready=0,
    )
    result = EnrichmentResult(path="/music/test.flac", matches=[tidal_match])

    ok = update_database(db_path=db_path, result=result, dry_run=False, mode="recovery")
    assert ok is True

    check_conn = sqlite3.connect(db_path)
    try:
        row = check_conn.execute(
            """
            SELECT
                tidal_bpm,
                tidal_key,
                tidal_key_scale,
                tidal_camelot,
                replay_gain_track,
                replay_gain_album,
                tidal_dj_ready,
                tidal_stem_ready
            FROM track_identity
            WHERE id = ?
            """,
            (10,),
        ).fetchone()
    finally:
        check_conn.close()

    assert row is not None
    assert float(row[0]) == 120.0
    assert row[1] == "C"
    assert row[2] == "MINOR"
    assert row[3] == "11A"
    assert float(row[4]) == -8.0
    assert float(row[5]) == -7.5
    assert int(row[6]) == 1
    assert int(row[7]) == 0
