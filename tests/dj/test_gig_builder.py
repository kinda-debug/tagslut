import sqlite3
from pathlib import Path
from unittest.mock import patch

from tagslut.exec.gig_builder import GigBuilder
from tagslut.exec.transcoder import TranscodeError
from tagslut.storage.schema import init_db


def _insert_file(
    conn: sqlite3.Connection,
    *,
    path: Path,
    checksum: str,
    is_dj_material: int = 1,
    genre: str | None = None,
    bpm: float | None = None,
    dj_pool_path: Path | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO files (
            path, checksum, duration, bit_depth, sample_rate, bitrate,
            metadata_json, quality_rank, is_dj_material, canonical_genre, canonical_bpm, dj_pool_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(path),
            checksum,
            300.0,
            16,
            44100,
            0,
            "{}",
            4,
            is_dj_material,
            genre,
            bpm,
            str(dj_pool_path) if dj_pool_path else None,
        ),
    )


def _setup_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_build_full_flow_transcode_copy_record(tmp_path: Path) -> None:
    conn = _setup_db()
    try:
        usb = tmp_path / "usb"
        pool = tmp_path / "pool"
        usb.mkdir()
        pool.mkdir()

        flac_a = tmp_path / "a.flac"
        flac_b = tmp_path / "b.flac"
        flac_missing = tmp_path / "missing.flac"
        flac_a.write_bytes(b"a")
        flac_b.write_bytes(b"b")
        existing_mp3 = pool / "b.mp3"
        existing_mp3.write_bytes(b"mp3")

        _insert_file(conn, path=flac_a, checksum="sha-a", genre="techno", bpm=130.0)
        _insert_file(conn, path=flac_b, checksum="sha-b", genre="techno", bpm=130.0, dj_pool_path=existing_mp3)
        _insert_file(conn, path=flac_missing, checksum="sha-c", genre="techno", bpm=130.0)
        conn.commit()

        transcoded_mp3 = pool / "a.mp3"
        dest_a = usb / "MUSIC" / "Test Set" / "a.mp3"
        dest_b = usb / "MUSIC" / "Test Set" / "b.mp3"
        manifest = usb / "gig_manifest.txt"

        with patch("tagslut.exec.gig_builder.transcode_to_mp3", return_value=transcoded_mp3) as mock_transcode, patch(
            "tagslut.exec.gig_builder.copy_to_usb", return_value=[dest_a, dest_b]
        ) as mock_copy, patch("tagslut.exec.gig_builder.write_rekordbox_db") as mock_rb, patch(
            "tagslut.exec.gig_builder.write_manifest", return_value=manifest
        ) as mock_manifest:
            result = GigBuilder(conn, dj_pool_dir=pool).build(
                "Test Set",
                "genre:techno dj_flag:true",
                usb,
                dry_run=False,
            )

        assert result.tracks_found == 3
        assert result.tracks_transcoded == 1
        assert result.tracks_skipped == 1
        assert result.tracks_copied == 2
        assert len(result.errors) == 1
        assert "Master not found" in result.errors[0]
        assert result.manifest_path == manifest

        mock_transcode.assert_called_once_with(flac_a, pool, bitrate=320)
        assert mock_copy.call_args.args[0] == [transcoded_mp3, existing_mp3]
        mock_rb.assert_called_once()
        mock_manifest.assert_called_once()

        row = conn.execute(
            "SELECT dj_pool_path, last_exported_usb FROM files WHERE path = ?",
            (str(flac_a),),
        ).fetchone()
        assert row[0] == str(transcoded_mp3)
        assert row[1] is not None
        prov = conn.execute(
            "SELECT event_type, status, source_path, dest_path FROM provenance_event ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert prov is not None
        assert prov[0] == "dj_export"
        assert prov[1] == "success"
        assert prov[2] == str(flac_a)
        assert prov[3] == str(transcoded_mp3)

        gig_row = conn.execute(
            "SELECT name, track_count, usb_path, filter_expr FROM gig_sets ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert gig_row[0] == "Test Set"
        assert gig_row[1] == 2
        assert gig_row[2] == str(usb)
        assert "genre:techno" in gig_row[3]

        track_rows = conn.execute(
            "SELECT file_path, mp3_path, usb_dest_path FROM gig_set_tracks ORDER BY id"
        ).fetchall()
        assert len(track_rows) == 2
        assert track_rows[0][0] == str(flac_a)
        assert track_rows[0][1] == str(transcoded_mp3)
        assert track_rows[0][2] == str(dest_a)
    finally:
        conn.close()


def test_build_dry_run_plans_without_writes(tmp_path: Path) -> None:
    conn = _setup_db()
    try:
        usb = tmp_path / "usb"
        pool = tmp_path / "pool"
        usb.mkdir()
        pool.mkdir()

        flac = tmp_path / "track.flac"
        flac.write_bytes(b"x")
        _insert_file(conn, path=flac, checksum="sha-1", genre="techno", bpm=128.0)
        conn.commit()

        with (
            patch(
                "tagslut.exec.gig_builder.copy_to_usb",
                return_value=[usb / "MUSIC" / "Dry" / "track.mp3"],
            ) as mock_copy,
            patch("tagslut.exec.gig_builder.write_rekordbox_db") as mock_rb,
            patch("tagslut.exec.gig_builder.write_manifest") as mock_manifest,
            patch("tagslut.exec.gig_builder.transcode_to_mp3") as mock_transcode,
        ):
            result = GigBuilder(conn, dj_pool_dir=pool).build("Dry", "dj_flag:true", usb, dry_run=True)

        assert result.tracks_found == 1
        assert result.tracks_transcoded == 1
        assert result.tracks_copied == 1
        assert result.manifest_path is None

        mock_transcode.assert_not_called()
        mock_copy.assert_not_called()
        mock_rb.assert_not_called()
        mock_manifest.assert_not_called()

        gig_rows = conn.execute("SELECT COUNT(*) FROM gig_sets").fetchone()[0]
        assert gig_rows == 0
        db_row = conn.execute(
            "SELECT dj_pool_path, last_exported_usb FROM files WHERE path = ?",
            (str(flac),),
        ).fetchone()
        assert db_row[0] is None
        assert db_row[1] is None
    finally:
        conn.close()


def test_build_applies_filter_expression(tmp_path: Path) -> None:
    conn = _setup_db()
    try:
        usb = tmp_path / "usb"
        pool = tmp_path / "pool"
        usb.mkdir()
        pool.mkdir()

        flac_techno = tmp_path / "techno.flac"
        flac_house = tmp_path / "house.flac"
        flac_techno.write_bytes(b"1")
        flac_house.write_bytes(b"2")

        _insert_file(conn, path=flac_techno, checksum="sha-t", genre="techno", bpm=130.0)
        _insert_file(conn, path=flac_house, checksum="sha-h", genre="house", bpm=124.0)
        conn.commit()

        with patch("tagslut.exec.gig_builder.copy_to_usb", return_value=[]), patch(
            "tagslut.exec.gig_builder.write_rekordbox_db"
        ):
            result = GigBuilder(conn, dj_pool_dir=pool).build("Techno", "genre:techno", usb, dry_run=True)

        assert result.tracks_found == 1
    finally:
        conn.close()


def test_build_collects_transcode_errors_and_continues(tmp_path: Path) -> None:
    conn = _setup_db()
    try:
        usb = tmp_path / "usb"
        pool = tmp_path / "pool"
        usb.mkdir()
        pool.mkdir()

        flac_1 = tmp_path / "a.flac"
        flac_2 = tmp_path / "b.flac"
        flac_1.write_bytes(b"a")
        flac_2.write_bytes(b"b")
        _insert_file(conn, path=flac_1, checksum="sha-1", genre="techno", bpm=130.0)
        _insert_file(conn, path=flac_2, checksum="sha-2", genre="techno", bpm=130.0)
        conn.commit()

        good_mp3 = pool / "ok.mp3"

        def _fake_transcode(src: Path, _dest: Path, bitrate: int = 320):
            if src == flac_1:
                raise TranscodeError("boom")
            return good_mp3

        with patch("tagslut.exec.gig_builder.transcode_to_mp3", side_effect=_fake_transcode), patch(
            "tagslut.exec.gig_builder.copy_to_usb", return_value=[usb / "MUSIC" / "Set" / "ok.mp3"]
        ), patch("tagslut.exec.gig_builder.write_rekordbox_db"), patch(
            "tagslut.exec.gig_builder.write_manifest", return_value=usb / "manifest.txt"
        ):
            result = GigBuilder(conn, dj_pool_dir=pool).build("Set", "genre:techno", usb, dry_run=False)

        assert result.tracks_found == 2
        assert result.tracks_transcoded == 1
        assert result.tracks_copied == 1
        assert any("boom" in err for err in result.errors)

        gig_row = conn.execute("SELECT track_count FROM gig_sets ORDER BY id DESC LIMIT 1").fetchone()
        assert gig_row[0] == 1
    finally:
        conn.close()


def test_build_reuses_existing_dj_pool_mp3_without_transcode(tmp_path: Path) -> None:
    conn = _setup_db()
    try:
        usb = tmp_path / "usb"
        pool = tmp_path / "pool"
        usb.mkdir()
        pool.mkdir()

        flac = tmp_path / "track.flac"
        flac.write_bytes(b"x")
        existing_mp3 = pool / "existing.mp3"
        existing_mp3.write_bytes(b"mp3")

        _insert_file(conn, path=flac, checksum="sha-1", genre="techno", bpm=130.0, dj_pool_path=existing_mp3)
        conn.commit()

        with patch("tagslut.exec.gig_builder.transcode_to_mp3") as mock_transcode, patch(
            "tagslut.exec.gig_builder.copy_to_usb", return_value=[usb / "MUSIC" / "Reuse" / "existing.mp3"]
        ), patch("tagslut.exec.gig_builder.write_rekordbox_db"), patch(
            "tagslut.exec.gig_builder.write_manifest", return_value=usb / "manifest.txt"
        ):
            result = GigBuilder(conn, dj_pool_dir=pool).build("Reuse", "dj_flag:true", usb, dry_run=False)

        mock_transcode.assert_not_called()
        assert result.tracks_skipped == 1
        assert result.tracks_copied == 1

        exported = conn.execute("SELECT last_exported_usb FROM files WHERE path = ?", (str(flac),)).fetchone()[0]
        assert exported is not None
    finally:
        conn.close()


def test_build_reuses_latest_dj_export_receipt_without_dj_pool_path(tmp_path: Path) -> None:
    conn = _setup_db()
    try:
        usb = tmp_path / "usb"
        pool = tmp_path / "pool"
        usb.mkdir()
        pool.mkdir()

        flac = tmp_path / "track.flac"
        flac.write_bytes(b"x")
        exported_mp3 = pool / "receipt.mp3"
        exported_mp3.write_bytes(b"mp3")

        _insert_file(conn, path=flac, checksum="sha-1", genre="techno", bpm=130.0)
        conn.execute(
            """
            INSERT INTO provenance_event (event_type, status, source_path, dest_path)
            VALUES ('dj_export', 'success', ?, ?)
            """,
            (str(flac), str(exported_mp3)),
        )
        conn.commit()

        with patch("tagslut.exec.gig_builder.transcode_to_mp3") as mock_transcode, patch(
            "tagslut.exec.gig_builder.copy_to_usb", return_value=[usb / "MUSIC" / "Reuse" / "receipt.mp3"]
        ), patch("tagslut.exec.gig_builder.write_rekordbox_db"), patch(
            "tagslut.exec.gig_builder.write_manifest", return_value=usb / "manifest.txt"
        ):
            result = GigBuilder(conn, dj_pool_dir=pool).build("Reuse", "dj_flag:true", usb, dry_run=False)

        mock_transcode.assert_not_called()
        assert result.tracks_skipped == 1
        assert result.tracks_copied == 1
    finally:
        conn.close()
