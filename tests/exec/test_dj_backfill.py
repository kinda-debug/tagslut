"""CLI-level tests for `tagslut dj backfill` (Stage 3 bulk admission)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from tagslut.cli.main import cli
from tagslut.exec.dj_backfill import MP3_RECONCILE_SUCCESS_STATUS
from tagslut.storage.schema import init_db
from tests.conftest import PROV_COLS, PROV_VALS


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.commit()
    conn.close()
    return db_path


def _insert_identity(conn: sqlite3.Connection, *, title: str, artist: str, isrc: str) -> int:
    cur = conn.execute(
        f"INSERT INTO track_identity (title_norm, artist_norm, isrc, identity_key{PROV_COLS})"
        f" VALUES (?, ?, ?, ?{PROV_VALS})",
        (title, artist, isrc, isrc),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def _insert_asset_file(conn: sqlite3.Connection, *, path: str) -> int:
    cur = conn.execute(
        "INSERT INTO asset_file (path, size_bytes) VALUES (?, 0)",
        (path,),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def _insert_mp3_asset(
    conn: sqlite3.Connection,
    *,
    identity_id: int,
    asset_id: int,
    path: str,
    profile: str = "dj_copy_320_cbr",
    status: str = MP3_RECONCILE_SUCCESS_STATUS,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO mp3_asset (identity_id, asset_id, profile, path, status, transcoded_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        (identity_id, asset_id, profile, path, status),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def test_dj_backfill_idempotent_prints_summary(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(str(db_path))
    identity_id = _insert_identity(conn, title="Track A", artist="Artist A", isrc="ISRC-A")
    asset_id = _insert_asset_file(conn, path="/lib/a.flac")
    _insert_mp3_asset(conn, identity_id=identity_id, asset_id=asset_id, path="/dj/a.mp3")
    conn.close()

    runner = CliRunner()

    r1 = runner.invoke(cli, ["dj", "backfill", "--db", str(db_path), "--execute"])
    assert r1.exit_code == 0, r1.output
    assert "Admitted 1 new, skipped 0 existing." in r1.output

    r2 = runner.invoke(cli, ["dj", "backfill", "--db", str(db_path), "--execute"])
    assert r2.exit_code == 0, r2.output
    assert "Admitted 0 new, skipped 1 existing." in r2.output

    conn = sqlite3.connect(str(db_path))
    admission_count = conn.execute("SELECT COUNT(*) FROM dj_admission").fetchone()[0]
    map_count = conn.execute("SELECT COUNT(*) FROM dj_track_id_map").fetchone()[0]
    conn.close()

    assert admission_count == 1
    assert map_count == 1

