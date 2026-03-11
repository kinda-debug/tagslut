from pathlib import Path

from tagslut.storage.models import AudioFile
from tagslut.storage.queries import _normalize_text_field, get_file, upsert_file
from tagslut.storage.schema import get_connection, init_db


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


def test_upsert_round_trips_dj_roles(tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    conn = get_connection(db_path)
    path = tmp_path / "set-track.flac"
    try:
        init_db(conn)
        audio = AudioFile(
            path=path,
            checksum="streaminfo:cafebabe",
            duration=1.0,
            bit_depth=16,
            sample_rate=44100,
            bitrate=900,
            metadata={"artist": "Test"},
            dj_set_role="bridge",
            dj_subrole="vocal",
        )
        upsert_file(conn, audio)
        conn.commit()

        stored = get_file(conn, path)

        assert stored is not None
        assert stored.dj_set_role == "bridge"
        assert stored.dj_subrole == "vocal"
    finally:
        conn.close()


def test_normalize_text_field_coalesces_dj_set_role_sequence() -> None:
    assert _normalize_text_field(["groove", "prime"], "dj_set_role") == "groove;prime"
