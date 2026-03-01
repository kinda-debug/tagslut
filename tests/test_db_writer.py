import sqlite3
from pathlib import Path

from tagslut.metadata.models.types import EnrichmentResult
from tagslut.metadata.store.db_writer import update_database
from tagslut.storage.schema import init_db


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
