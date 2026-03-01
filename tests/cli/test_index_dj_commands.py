from __future__ import annotations

import importlib
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

    migration = importlib.import_module("tagslut.storage.migrations.0002_add_dj_fields")
    migration.up(conn)

    conn.close()
    return db_path


def _insert_file(
    db_path: Path,
    *,
    path: str,
    checksum: str,
    isrc: str | None = None,
    genre: str | None = None,
    canonical_genre: str | None = None,
    bpm: float | None = None,
    canonical_bpm: float | None = None,
    canonical_label: str | None = None,
    dj_flag: int = 0,
    last_exported_usb: str | None = None,
    key_camelot: str | None = None,
    dj_pool_path: str | None = None,
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO files (
            path, checksum, metadata_json, isrc, genre, canonical_genre,
            bpm, canonical_bpm, canonical_label, dj_flag,
            last_exported_usb, key_camelot, dj_pool_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            path,
            checksum,
            "{}",
            isrc,
            genre,
            canonical_genre,
            bpm,
            canonical_bpm,
            canonical_label,
            dj_flag,
            last_exported_usb,
            key_camelot,
            dj_pool_path,
        ),
    )
    conn.commit()
    conn.close()


def _fetch_flag(db_path: Path, track_path: str) -> int:
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT dj_flag FROM files WHERE path = ?", (track_path,)).fetchone()
    conn.close()
    assert row is not None
    return int(row[0])


def test_dj_flag_by_path_updates_row(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    track_path = "/music/a.flac"
    _insert_file(db_path, path=track_path, checksum="a1")

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-flag", track_path, "--set", "true", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "dj_flag set to 1 for 1 row(s)" in result.output
    assert _fetch_flag(db_path, track_path) == 1


def test_dj_flag_by_isrc_updates_all_matching_rows(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(db_path, path="/music/a.flac", checksum="a1", isrc="USAAA111")
    _insert_file(db_path, path="/music/b.flac", checksum="b1", isrc="USAAA111")

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-flag", "USAAA111", "--set", "true", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "for 2 row(s) matching 'USAAA111'" in result.output
    assert _fetch_flag(db_path, "/music/a.flac") == 1
    assert _fetch_flag(db_path, "/music/b.flac") == 1


def test_dj_flag_set_false_unflags_row(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    track_path = "/music/c.flac"
    _insert_file(db_path, path=track_path, checksum="c1", dj_flag=1)

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-flag", track_path, "--set", "false", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "dj_flag set to 0 for 1 row(s)" in result.output
    assert _fetch_flag(db_path, track_path) == 0


def test_dj_flag_nonexistent_target_updates_zero_rows(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(db_path, path="/music/a.flac", checksum="a1", isrc="USX")

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-flag", "NO_MATCH", "--set", "true", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "for 0 row(s) matching 'NO_MATCH'" in result.output
    assert _fetch_flag(db_path, "/music/a.flac") == 0


def test_dj_autoflag_genre_filter_flags_matching_rows(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(db_path, path="/music/t1.flac", checksum="1", genre="Techno")
    _insert_file(db_path, path="/music/t2.flac", checksum="2", canonical_genre="Deep Techno")
    _insert_file(db_path, path="/music/h1.flac", checksum="3", genre="House")

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-autoflag", "--genre", "techno", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "dj_flag set to 1 for 2 row(s)." in result.output
    assert _fetch_flag(db_path, "/music/t1.flac") == 1
    assert _fetch_flag(db_path, "/music/t2.flac") == 1
    assert _fetch_flag(db_path, "/music/h1.flac") == 0


def test_dj_autoflag_bpm_range_flags_matching_rows(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(db_path, path="/music/a.flac", checksum="1", bpm=128.0)
    _insert_file(db_path, path="/music/b.flac", checksum="2", canonical_bpm=131.0)
    _insert_file(db_path, path="/music/c.flac", checksum="3", bpm=150.0)

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-autoflag", "--bpm", "127-132", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "dj_flag set to 1 for 2 row(s)." in result.output
    assert _fetch_flag(db_path, "/music/a.flac") == 1
    assert _fetch_flag(db_path, "/music/b.flac") == 1
    assert _fetch_flag(db_path, "/music/c.flac") == 0


def test_dj_autoflag_label_filter_flags_matching_rows(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(db_path, path="/music/a.flac", checksum="1", canonical_label="Drumcode")
    _insert_file(db_path, path="/music/b.flac", checksum="2", canonical_label="Afterlife")

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-autoflag", "--label", "drum", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "dj_flag set to 1 for 1 row(s)." in result.output
    assert _fetch_flag(db_path, "/music/a.flac") == 1
    assert _fetch_flag(db_path, "/music/b.flac") == 0


def test_dj_autoflag_combined_filters_use_intersection(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(
        db_path,
        path="/music/match.flac",
        checksum="1",
        genre="Techno",
        bpm=130.0,
        canonical_label="Drumcode",
    )
    _insert_file(
        db_path,
        path="/music/genre_only.flac",
        checksum="2",
        genre="Techno",
        bpm=118.0,
        canonical_label="Drumcode",
    )
    _insert_file(
        db_path,
        path="/music/bpm_label_only.flac",
        checksum="3",
        genre="House",
        bpm=130.0,
        canonical_label="Drumcode",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "index",
            "dj-autoflag",
            "--genre",
            "techno",
            "--bpm",
            "125-135",
            "--label",
            "drum",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert "dj_flag set to 1 for 1 row(s)." in result.output
    assert _fetch_flag(db_path, "/music/match.flac") == 1
    assert _fetch_flag(db_path, "/music/genre_only.flac") == 0
    assert _fetch_flag(db_path, "/music/bpm_label_only.flac") == 0


def test_dj_autoflag_invalid_bpm_range_shows_error(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(db_path, path="/music/a.flac", checksum="1", bpm=128.0)

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-autoflag", "--bpm", "bad-range", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Invalid BPM range 'bad-range'. Expected format: '125-145'." in result.output
    assert _fetch_flag(db_path, "/music/a.flac") == 0


def test_dj_autoflag_without_filters_shows_error(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-autoflag", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Provide at least one filter (--genre, --bpm, --label)." in result.output


def test_dj_status_empty_db_shows_zeros(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-status", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Total tracks:         0" in result.output
    assert "DJ-flagged:           0" in result.output
    assert "In DJ pool (MP3):     0" in result.output
    assert "Exported to USB:      0" in result.output


def test_dj_status_mixed_flagged_unflagged_counts(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(db_path, path="/music/a.flac", checksum="1", dj_flag=1, bpm=128.0, key_camelot="8A", isrc="USA")
    _insert_file(db_path, path="/music/b.flac", checksum="2", dj_flag=0)
    _insert_file(db_path, path="/music/c.flac", checksum="3", dj_flag=1)

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-status", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "Total tracks:         3" in result.output
    assert "DJ-flagged:           2" in result.output
    assert "Have BPM:             1" in result.output
    assert "Have Camelot key:     1" in result.output
    assert "Have ISRC:            1" in result.output


def test_dj_status_counts_exported_tracks(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(
        db_path,
        path="/music/a.flac",
        checksum="1",
        dj_flag=1,
        dj_pool_path="/pool/a.mp3",
        last_exported_usb="2026-03-01T00:00:00Z",
    )
    _insert_file(db_path, path="/music/b.flac", checksum="2", dj_flag=1, dj_pool_path="/pool/b.mp3")

    runner = CliRunner()
    result = runner.invoke(cli, ["index", "dj-status", "--db", str(db_path)])

    assert result.exit_code == 0
    assert "In DJ pool (MP3):     2" in result.output
    assert "Exported to USB:      1" in result.output
