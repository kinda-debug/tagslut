import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from tagslut.exec.gig_builder import GigBuilder
from tagslut.storage.schema import init_db


@pytest.fixture
def db_with_dj_tracks(tmp_path: Path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    for i in range(2):
        flac = tmp_path / f"track{i}.flac"
        flac.write_bytes(b"fake")
        conn.execute(
            """
            INSERT INTO files (
                path, checksum, duration, bit_depth, sample_rate, bitrate,
                metadata_json, quality_rank, is_dj_material, canonical_genre, canonical_bpm
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(flac), f"abc{i}", 300.0, 16, 44100, 0, "{}", 4, 1, "techno", 132.0),
        )
    conn.commit()
    yield conn, tmp_path
    conn.close()


def test_gig_build_dry_run_finds_tracks_and_makes_no_writes(db_with_dj_tracks, tmp_path: Path):
    conn, _ = db_with_dj_tracks
    usb = tmp_path / "usb"
    usb.mkdir()
    pool = tmp_path / "pool"
    pool.mkdir()

    with patch("tagslut.exec.gig_builder.transcode_to_mp3") as mock_transcode, patch(
        "tagslut.exec.gig_builder.copy_to_usb"
    ) as mock_copy, patch("tagslut.exec.gig_builder.write_rekordbox_db") as mock_rb, patch(
        "tagslut.exec.gig_builder.write_manifest"
    ) as mock_manifest:
        builder = GigBuilder(conn, dj_pool_dir=pool)
        result = builder.build("Test Gig", "dj_flag:true", usb, dry_run=True)

    assert result.tracks_found == 2
    assert result.gig_name == "Test Gig"
    mock_transcode.assert_not_called()
    mock_copy.assert_not_called()
    mock_rb.assert_not_called()
    mock_manifest.assert_not_called()

    gig_rows = conn.execute("SELECT COUNT(*) FROM gig_sets").fetchone()[0]
    assert gig_rows == 0


def test_gig_build_no_match_returns_zero(db_with_dj_tracks, tmp_path: Path):
    conn, _ = db_with_dj_tracks
    usb = tmp_path / "usb"
    usb.mkdir()

    builder = GigBuilder(conn, dj_pool_dir=tmp_path / "pool")
    result = builder.build("Empty", "genre:jazz", usb, dry_run=True)

    assert result.tracks_found == 0
