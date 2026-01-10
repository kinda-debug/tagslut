from pathlib import Path

from dedupe.storage.models import AudioFile
from dedupe.storage.queries import upsert_file
from dedupe.storage.schema import get_connection, init_db


def test_upsert_normalizes_tuple_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    conn = get_connection(db_path)
    try:
        init_db(conn)
        audio = AudioFile(
            path=tmp_path / "song.flac",
            checksum="streaminfo:deadbeef",
            duration=1.0,
            bit_depth=16,
            sample_rate=44100,
            bitrate=900,
            metadata={"artist": "Test"},
            flac_ok=True,
            acoustid=("x", "y"),  # type: ignore[arg-type]
            integrity_state=("valid", "detail"),  # type: ignore[arg-type]
        )
        upsert_file(conn, audio)
        conn.commit()

        row = conn.execute("SELECT acoustid, integrity_state FROM files").fetchone()
        assert row["acoustid"] == "x"
        assert row["integrity_state"] == "valid"
    finally:
        conn.close()
