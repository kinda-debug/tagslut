"""Tests for tagslut.dj.admission — admit, backfill, validate."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tagslut.dj.admission import (
    DjAdmissionError,
    admit_track,
    backfill_admissions,
    validate_dj_library,
)
from tagslut.storage.schema import init_db
from tests.conftest import PROV_COLS, PROV_VALS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.commit()
    return conn


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
    status: str = "verified",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO mp3_asset (identity_id, asset_id, profile, path, status, transcoded_at)
        VALUES (?, ?, 'mp3_320_cbr', ?, ?, datetime('now'))
        """,
        (identity_id, asset_id, path, status),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# admit_track
# ---------------------------------------------------------------------------


def test_admit_track_creates_row(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Song A", artist="Artist A", isrc="ISRC-A")
    asset_id = _insert_asset_file(conn, path="/lib/song_a.flac")
    mp3_id = _insert_mp3_asset(conn, identity_id=identity_id, asset_id=asset_id, path="/dj/song_a.mp3")

    admission_id = admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)

    row = conn.execute("SELECT id, status FROM dj_admission WHERE id = ?", (admission_id,)).fetchone()
    assert row is not None
    assert row[1] == "admitted"


def test_admit_track_raises_if_already_active(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Song B", artist="Artist B", isrc="ISRC-B")
    asset_id = _insert_asset_file(conn, path="/lib/song_b.flac")
    mp3_id = _insert_mp3_asset(conn, identity_id=identity_id, asset_id=asset_id, path="/dj/song_b.mp3")

    admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
    conn.commit()

    with pytest.raises(DjAdmissionError, match="already admitted"):
        admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)


def test_admit_track_reactivates_retired_admission(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Song C", artist="Artist C", isrc="ISRC-C")
    asset_id = _insert_asset_file(conn, path="/lib/song_c.flac")
    mp3_id = _insert_mp3_asset(conn, identity_id=identity_id, asset_id=asset_id, path="/dj/song_c.mp3")

    admission_id = admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
    conn.execute("UPDATE dj_admission SET status = 'rejected' WHERE id = ?", (admission_id,))
    conn.commit()

    # Should re-activate without raising
    returned_id = admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
    conn.commit()
    assert returned_id == admission_id

    row = conn.execute("SELECT status FROM dj_admission WHERE id = ?", (admission_id,)).fetchone()
    assert row[0] == "admitted"


# ---------------------------------------------------------------------------
# backfill_admissions
# ---------------------------------------------------------------------------


def test_backfill_admits_unlinked_mp3_assets(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Song D", artist="Artist D", isrc="ISRC-D")
    asset_id = _insert_asset_file(conn, path="/lib/song_d.flac")
    _insert_mp3_asset(conn, identity_id=identity_id, asset_id=asset_id, path="/dj/song_d.mp3")

    admitted, skipped = backfill_admissions(conn)
    conn.commit()

    assert admitted == 1
    assert skipped == 0
    count = conn.execute("SELECT COUNT(*) FROM dj_admission WHERE status = 'admitted'").fetchone()[0]
    assert count == 1


def test_backfill_skips_already_active(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Song E", artist="Artist E", isrc="ISRC-E")
    asset_id = _insert_asset_file(conn, path="/lib/song_e.flac")
    mp3_id = _insert_mp3_asset(conn, identity_id=identity_id, asset_id=asset_id, path="/dj/song_e.mp3")
    admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
    conn.commit()

    admitted, skipped = backfill_admissions(conn)
    assert admitted == 0
    assert skipped == 0  # no new un-admitted rows to even encounter


def test_backfill_ignores_non_verified_mp3_assets(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Song F", artist="Artist F", isrc="ISRC-F")
    asset_id = _insert_asset_file(conn, path="/lib/song_f.flac")
    _insert_mp3_asset(conn, identity_id=identity_id, asset_id=asset_id, path="/dj/song_f.mp3", status="missing")

    admitted, skipped = backfill_admissions(conn)
    assert admitted == 0


# ---------------------------------------------------------------------------
# validate_dj_library
# ---------------------------------------------------------------------------


def test_validate_passes_when_clean(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Valid Track", artist="Valid Artist", isrc="ISRC-V")
    asset_id = _insert_asset_file(conn, path="/lib/valid.flac")
    mp3_file = tmp_path / "valid.mp3"
    mp3_file.write_bytes(b"")
    mp3_id = _insert_mp3_asset(conn, identity_id=identity_id, asset_id=asset_id, path=str(mp3_file))
    admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
    conn.commit()

    report = validate_dj_library(conn)
    assert report.ok, f"Expected no issues but got: {report.summary()}"


def test_validate_detects_missing_mp3_file(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Missing MP3", artist="Artist M", isrc="ISRC-M")
    asset_id = _insert_asset_file(conn, path="/lib/missing.flac")
    mp3_id = _insert_mp3_asset(
        conn,
        identity_id=identity_id,
        asset_id=asset_id,
        path="/nonexistent/path/missing.mp3",
    )
    admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
    conn.commit()

    report = validate_dj_library(conn)
    assert not report.ok
    kinds = {i.kind for i in report.issues}
    assert "MISSING_MP3_FILE" in kinds


def test_validate_detects_missing_metadata(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    # Insert identity with empty title
    cur = conn.execute(
        f"INSERT INTO track_identity (title_norm, artist_norm, isrc, identity_key{PROV_COLS})"
        f" VALUES (?, ?, ?, ?{PROV_VALS})",
        ("", "Artist N", "ISRC-N", "ISRC-N"),
    )
    identity_id = cur.lastrowid
    conn.commit()

    asset_id = _insert_asset_file(conn, path="/lib/no_title.flac")
    mp3_file = tmp_path / "no_title.mp3"
    mp3_file.write_bytes(b"")
    mp3_id = _insert_mp3_asset(
        conn, identity_id=identity_id, asset_id=asset_id, path=str(mp3_file)
    )
    admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
    conn.commit()

    report = validate_dj_library(conn)
    assert not report.ok
    kinds = {i.kind for i in report.issues}
    assert "MISSING_METADATA" in kinds


def test_validate_ok_with_multiple_distinct_admissions(tmp_path: Path) -> None:
    """validate_dj_library should pass when multiple tracks each have distinct MP3 paths."""
    conn = _make_db(tmp_path)

    for n in range(3):
        mp3_file = tmp_path / f"track_{n}.mp3"
        mp3_file.write_bytes(b"")
        identity_id = _insert_identity(
            conn, title=f"Track {n}", artist="Artist", isrc=f"ISRC-MULTI-{n}"
        )
        asset_id = _insert_asset_file(conn, path=f"/lib/track_{n}.flac")
        mp3_id = _insert_mp3_asset(
            conn, identity_id=identity_id, asset_id=asset_id, path=str(mp3_file)
        )
        admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
        conn.commit()

    report = validate_dj_library(conn)
    assert report.ok, f"Expected no issues but got: {report.summary()}"
