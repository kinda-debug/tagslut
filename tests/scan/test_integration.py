import sqlite3
import wave
from pathlib import Path

from tagslut.scan.dedupe import mark_format_duplicates
from tagslut.scan.orchestrator import run_scan
from tagslut.storage.schema import init_db


def _write_minimal_wav(path: Path, *, seconds: float = 0.1, sample_rate: int = 44100) -> None:
    frame_count = max(1, int(seconds * sample_rate))
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * frame_count)


def _build_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_run_scan_end_to_end_with_real_wav(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    _write_minimal_wav(library / "ok.wav")

    conn = _build_db(tmp_path / "scan.db")
    try:
        run_id = run_scan(conn, library)

        run_row = conn.execute("SELECT completed_at, tool_versions_json FROM scan_runs WHERE id = ?", (run_id,)).fetchone()
        assert run_row is not None
        assert run_row["completed_at"] is not None
        assert "COMPLETE" in run_row["tool_versions_json"]

        file_row = conn.execute(
            "SELECT path, scan_status, checksum FROM files WHERE path = ?",
            (str(library / "ok.wav"),),
        ).fetchone()
        assert file_row is not None
        assert file_row["scan_status"] in {"CLEAN", "CORRUPT"}
        assert file_row["checksum"]
    finally:
        conn.close()


def test_run_scan_records_issue_for_corrupt_audio_file(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    bad = library / "bad.wav"
    bad.write_bytes(b"not-a-real-wav")

    conn = _build_db(tmp_path / "scan.db")
    try:
        run_id = run_scan(conn, library)

        issue = conn.execute(
            "SELECT issue_code, severity FROM scan_issues WHERE run_id = ? ORDER BY id ASC LIMIT 1",
            (run_id,),
        ).fetchone()
        assert issue is not None
        assert issue["issue_code"] == "TAGS_UNREADABLE"
        assert issue["severity"] == "ERROR"

        file_row = conn.execute("SELECT scan_status FROM files WHERE path = ?", (str(bad),)).fetchone()
        assert file_row is not None
        assert file_row["scan_status"] == "CORRUPT"
    finally:
        conn.close()


def test_run_scan_followed_by_dedupe_elects_format_duplicate(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    a = library / "a.wav"
    b = library / "b.wav"
    _write_minimal_wav(a, seconds=0.2)
    _write_minimal_wav(b, seconds=0.1)

    conn = _build_db(tmp_path / "scan.db")
    try:
        run_scan(conn, library)

        conn.execute(
            "UPDATE files SET canonical_isrc = ?, identity_confidence = ?, quality_rank = ?, checksum = ? WHERE path = ?",
            ("USABC1234567", 70, 4, "checksum_a", str(a)),
        )
        conn.execute(
            "UPDATE files SET canonical_isrc = ?, identity_confidence = ?, quality_rank = ?, checksum = ? WHERE path = ?",
            ("USABC1234567", 85, 2, "checksum_b", str(b)),
        )
        conn.commit()

        marked = mark_format_duplicates(conn)
        assert marked == 1

        dup_row = conn.execute(
            "SELECT scan_status, duplicate_of_checksum FROM files WHERE path = ?",
            (str(a),),
        ).fetchone()
        assert dup_row is not None
        assert dup_row["scan_status"] == "FORMAT_DUPLICATE"
        assert dup_row["duplicate_of_checksum"] == "checksum_b"
    finally:
        conn.close()


def test_run_scan_uses_isolated_tmp_db_state(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    _write_minimal_wav(library / "only.wav")

    conn_a = _build_db(tmp_path / "a.db")
    conn_b = _build_db(tmp_path / "b.db")
    try:
        run_scan(conn_a, library)

        count_a = conn_a.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
        count_b = conn_b.execute("SELECT COUNT(*) FROM scan_runs").fetchone()[0]
        assert count_a == 1
        assert count_b == 0
    finally:
        conn_a.close()
        conn_b.close()
