from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

import tagslut.cli.dj_role as dj_role_cli
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


def _insert_file(
    db_path: Path,
    *,
    path: str,
    checksum: str,
    is_dj_material: int = 0,
    dj_flag: int = 0,
    artist: str | None = None,
    title: str | None = None,
    bpm: float | None = None,
    key_camelot: str | None = None,
    genre: str | None = None,
    dj_set_role: str | None = None,
    dj_subrole: str | None = None,
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO files (
            path,
            checksum,
            metadata_json,
            is_dj_material,
            dj_flag,
            canonical_artist,
            canonical_title,
            bpm,
            key_camelot,
            genre,
            dj_set_role,
            dj_subrole
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            path,
            checksum,
            "{}",
            is_dj_material,
            dj_flag,
            artist,
            title,
            bpm,
            key_camelot,
            genre,
            dj_set_role,
            dj_subrole,
        ),
    )
    conn.commit()
    conn.close()


def _fetch_roles(db_path: Path, path: str) -> tuple[str | None, str | None]:
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT dj_set_role, dj_subrole FROM files WHERE path = ?",
        (path,),
    ).fetchone()
    conn.close()
    assert row is not None
    return row[0], row[1]


def _parse_csv_output(output: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(output))
    assert reader.fieldnames is not None
    return reader.fieldnames, list(reader)


def test_role_set_updates_db_row(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    track_path = "/music/a.flac"
    _insert_file(db_path, path=track_path, checksum="sum-a")

    runner = CliRunner()
    result = runner.invoke(cli, ["dj", "role", "set", track_path, "groove", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert f"SET  {track_path}  dj_set_role=groove" in result.output
    assert _fetch_roles(db_path, track_path) == ("groove", None)


def test_role_set_invalid_role_exits_non_zero_without_write(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    track_path = "/music/b.flac"
    _insert_file(db_path, path=track_path, checksum="sum-b")

    runner = CliRunner()
    result = runner.invoke(cli, ["dj", "role", "set", track_path, "bad-role", "--db", str(db_path)])

    assert result.exit_code != 0
    assert "Invalid dj_set_role" in result.output
    assert _fetch_roles(db_path, track_path) == (None, None)


def test_role_set_rejects_emergency(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    track_path = "/music/c.flac"
    _insert_file(db_path, path=track_path, checksum="sum-c")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["dj", "role", "set", track_path, "emergency", "--db", str(db_path)],
    )

    assert result.exit_code != 0
    assert "emergency" in result.output
    assert _fetch_roles(db_path, track_path) == (None, None)


def test_role_set_persists_valid_subrole(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    track_path = "/music/d.flac"
    _insert_file(db_path, path=track_path, checksum="sum-d")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["dj", "role", "set", track_path, "prime", "--subrole", "closer", "--db", str(db_path)],
    )

    assert result.exit_code == 0, result.output
    assert _fetch_roles(db_path, track_path) == ("prime", "closer")


def test_role_bulk_commits_valid_rows_and_skips_invalid_roles(
    tmp_path: Path,
    caplog,
) -> None:  # type: ignore[no-untyped-def]
    db_path = _create_db(tmp_path)
    _insert_file(db_path, path="/music/a.flac", checksum="sum-a")
    _insert_file(db_path, path="/music/b.flac", checksum="sum-b")

    csv_path = tmp_path / "roles.csv"
    csv_path.write_text(
        "path,dj_set_role,dj_subrole\n"
        "/music/a.flac,groove,tool\n"
        "/music/b.flac,not-a-role,closer\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    with caplog.at_level("WARNING", logger="tagslut.cli.dj_role"):
        result = runner.invoke(cli, ["dj", "role", "bulk", str(csv_path), "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert "Bulk role set: 1 updated, 1 skipped, 0 errors" in result.output
    assert "Invalid dj_set_role" in caplog.text
    assert _fetch_roles(db_path, "/music/a.flac") == ("groove", "tool")
    assert _fetch_roles(db_path, "/music/b.flac") == (None, None)


def test_role_bulk_rolls_back_on_mid_batch_error(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    db_path = _create_db(tmp_path)
    _insert_file(db_path, path="/music/a.flac", checksum="sum-a")
    _insert_file(db_path, path="/music/b.flac", checksum="sum-b")

    csv_path = tmp_path / "roles.csv"
    csv_path.write_text(
        "path,dj_set_role\n"
        "/music/a.flac,groove\n"
        "/music/b.flac,prime\n",
        encoding="utf-8",
    )

    original_update = dj_role_cli._update_role_path
    calls = {"count": 0}

    def _failing_update(
        conn: sqlite3.Connection,
        path: str,
        role: str,
        subrole: str | None,
        *,
        replace_subrole: bool,
    ) -> int:
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("boom")
        return original_update(
            conn,
            path,
            role,
            subrole,
            replace_subrole=replace_subrole,
        )

    monkeypatch.setattr(dj_role_cli, "_update_role_path", _failing_update)

    runner = CliRunner()
    result = runner.invoke(cli, ["dj", "role", "bulk", str(csv_path), "--db", str(db_path)])

    assert result.exit_code != 0
    assert "Bulk role update failed: boom" in result.output
    assert _fetch_roles(db_path, "/music/a.flac") == (None, None)
    assert _fetch_roles(db_path, "/music/b.flac") == (None, None)


def test_role_export_returns_dj_candidate_columns(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(
        db_path,
        path="/music/a.flac",
        checksum="sum-a",
        is_dj_material=1,
        artist="Artist A",
        title="Track A",
        bpm=128.0,
        key_camelot="8A",
        genre="Techno",
        dj_set_role="groove",
        dj_subrole="tool",
    )
    _insert_file(
        db_path,
        path="/music/b.flac",
        checksum="sum-b",
        is_dj_material=0,
        dj_flag=0,
        artist="Artist B",
        title="Track B",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["dj", "role", "export", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    fieldnames, rows = _parse_csv_output(result.output)
    assert fieldnames == [
        "path",
        "artist",
        "title",
        "bpm",
        "key_camelot",
        "genre",
        "dj_set_role",
        "dj_subrole",
    ]
    assert rows == [
        {
            "path": "/music/a.flac",
            "artist": "Artist A",
            "title": "Track A",
            "bpm": "128.0",
            "key_camelot": "8A",
            "genre": "Techno",
            "dj_set_role": "groove",
            "dj_subrole": "tool",
        }
    ]


def test_role_export_unassigned_only_returns_null_role_rows(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(
        db_path,
        path="/music/a.flac",
        checksum="sum-a",
        is_dj_material=1,
        artist="Artist A",
        title="Assigned",
        dj_set_role="prime",
    )
    _insert_file(
        db_path,
        path="/music/b.flac",
        checksum="sum-b",
        is_dj_material=1,
        artist="Artist B",
        title="Unassigned",
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["dj", "role", "export", "--unassigned-only", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    _, rows = _parse_csv_output(result.output)
    assert [row["path"] for row in rows] == ["/music/b.flac"]
    assert [row["dj_set_role"] for row in rows] == [""]
