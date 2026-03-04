from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from tagslut.cli.main import cli
from tagslut.storage.schema import init_db


def _create_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "inventory.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.close()
    return db_path


def _insert_gig_set_with_tracks(db_path: Path, usb_path: Path, expected_names: list[str]) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO gig_sets (name, filter_expr, usb_path, track_count, exported_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("Weekend Set", "dj_flag:true", str(usb_path), len(expected_names), "2026-03-01T10:00:00"),
    )
    gig_set_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    for name in expected_names:
        conn.execute(
            """
            INSERT INTO gig_set_tracks (gig_set_id, file_path, mp3_path, usb_dest_path, exported_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                gig_set_id,
                f"/library/{name}.flac",
                f"/dj_pool/{name}.mp3",
                str(usb_path / "MUSIC" / "Weekend Set" / f"{name}.mp3"),
                "2026-03-01T10:00:00",
            ),
        )
    conn.commit()
    conn.close()


def test_gig_status_complete_returns_zero(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    usb = tmp_path / "USB"
    music_dir = usb / "MUSIC" / "Weekend Set"
    music_dir.mkdir(parents=True)

    _insert_gig_set_with_tracks(db_path, usb, ["alpha", "beta"])
    (music_dir / "alpha.mp3").write_bytes(b"1")
    (music_dir / "beta.mp3").write_bytes(b"1")

    runner = CliRunner()
    result = runner.invoke(cli, ["gig", "status", "--usb", str(usb), "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Expected tracks: 2" in result.output
    assert "Current:         2" in result.output
    assert "Missing:         0" in result.output
    assert "Stale:           0" in result.output


def test_gig_status_missing_returns_exit_code_one(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    usb = tmp_path / "USB"
    music_dir = usb / "MUSIC" / "Weekend Set"
    music_dir.mkdir(parents=True)

    _insert_gig_set_with_tracks(db_path, usb, ["alpha", "beta"])
    (music_dir / "alpha.mp3").write_bytes(b"1")
    (music_dir / "stale.mp3").write_bytes(b"1")

    runner = CliRunner()
    result = runner.invoke(cli, ["gig", "status", "--usb", str(usb), "--db", str(db_path), "--verbose"])

    assert result.exit_code == 1
    assert "Current:         1" in result.output
    assert "Missing:         1" in result.output
    assert "Stale:           1" in result.output
    assert "Missing tracks:" in result.output
    assert "beta.mp3" in result.output
    assert "Stale tracks:" in result.output
    assert "stale.mp3" in result.output
