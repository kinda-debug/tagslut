from __future__ import annotations

import sqlite3
from pathlib import Path

from mutagen.id3 import ID3, TALB, TIT2, TPE1, TSRC

from tagslut.exec.mp3_build import reconcile_mp3_library
from tagslut.storage.schema import init_db
from tests.conftest import PROV_COLS, PROV_VALS


def _make_db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.commit()
    return conn


def _insert_identity(
    conn: sqlite3.Connection,
    *,
    title: str,
    artist: str,
    isrc: str,
) -> int:
    cur = conn.execute(
        f"INSERT INTO track_identity (title_norm, artist_norm, isrc, identity_key{PROV_COLS})"
        f" VALUES (?, ?, ?, ?{PROV_VALS})",
        (title, artist, isrc, isrc),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def _attach_master_asset(conn: sqlite3.Connection, *, identity_id: int, flac_path: str) -> None:
    asset_cur = conn.execute(
        "INSERT INTO asset_file (path, size_bytes) VALUES (?, 0)",
        (flac_path,),
    )
    asset_id = asset_cur.lastrowid
    conn.execute(
        "INSERT INTO asset_link (identity_id, asset_id, confidence) VALUES (?, ?, 1.0)",
        (identity_id, asset_id),
    )
    conn.commit()


def _write_id3_mp3(path: Path, *, title: str, artist: str, isrc: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text="Test Album"))
    if isrc:
        tags.add(TSRC(encoding=3, text=isrc))
    tags.save(str(path))


def test_isrc_match_produces_high_confidence(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)

    isrc_identity = _insert_identity(
        conn,
        title="Canonical Track",
        artist="Canonical Artist",
        isrc="ISRC-MATCH-001",
    )
    _attach_master_asset(conn, identity_id=isrc_identity, flac_path="/master/isrc_match.flac")

    decoy_identity = _insert_identity(
        conn,
        title="Tag Title",
        artist="Tag Artist",
        isrc="ISRC-DECOY-001",
    )
    _attach_master_asset(conn, identity_id=decoy_identity, flac_path="/master/decoy.flac")

    mp3_file = tmp_path / "dj" / "isrc_priority.mp3"
    _write_id3_mp3(
        mp3_file,
        title="Tag Title",
        artist="Tag Artist",
        isrc="ISRC-MATCH-001",
    )

    result = reconcile_mp3_library(conn, mp3_root=tmp_path / "dj", dry_run=False)

    row = conn.execute(
        "SELECT identity_id FROM mp3_asset WHERE path = ?",
        (str(mp3_file),),
    ).fetchone()
    assert result.linked == 1
    assert result.unmatched == 0
    assert row is not None
    assert row[0] == isrc_identity


def test_missing_isrc_title_artist_fallback(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)

    fallback_identity = _insert_identity(
        conn,
        title="Fallback Title",
        artist="Fallback Artist",
        isrc="ISRC-FALLBACK-001",
    )
    _attach_master_asset(conn, identity_id=fallback_identity, flac_path="/master/fallback.flac")

    mp3_file = tmp_path / "dj" / "fallback.mp3"
    _write_id3_mp3(
        mp3_file,
        title="Fallback Title",
        artist="Fallback Artist",
        isrc=None,
    )

    result = reconcile_mp3_library(conn, mp3_root=tmp_path / "dj", dry_run=False)

    row = conn.execute(
        "SELECT identity_id FROM mp3_asset WHERE path = ?",
        (str(mp3_file),),
    ).fetchone()
    assert result.linked == 1
    assert result.unmatched == 0
    assert row is not None
    assert row[0] == fallback_identity


def test_no_match_produces_suspect_status(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)

    mp3_file = tmp_path / "dj" / "unmatched.mp3"
    _write_id3_mp3(
        mp3_file,
        title="Unknown Title",
        artist="Unknown Artist",
        isrc=None,
    )

    result = reconcile_mp3_library(conn, mp3_root=tmp_path / "dj", dry_run=False)

    row = conn.execute(
        "SELECT identity_id, status, source FROM mp3_asset WHERE path = ?",
        (str(mp3_file),),
    ).fetchone()
    stub = conn.execute(
        "SELECT id, ingestion_method, ingestion_source FROM track_identity WHERE identity_key LIKE 'stub_%' AND ingestion_method='mp3_reconcile'"
    ).fetchone()
    assert result.linked == 0
    assert result.unmatched == 1
    assert row is not None
    assert row[1] == "unverified"
    assert row[2] == "mp3_reconcile"
    assert stub is not None
    assert stub[1] == "mp3_reconcile"
    assert stub[2] == "mp3_reconcile_stub"


def test_duplicate_isrc_handled_without_silent_skip(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)

    identity_id = _insert_identity(
        conn,
        title="Duplicate ISRC",
        artist="One Artist",
        isrc="ISRC-DUPE-001",
    )
    _attach_master_asset(conn, identity_id=identity_id, flac_path="/master/dupe.flac")

    first = tmp_path / "dj" / "dupe_1.mp3"
    second = tmp_path / "dj" / "dupe_2.mp3"
    _write_id3_mp3(first, title="Duplicate ISRC", artist="One Artist", isrc="ISRC-DUPE-001")
    _write_id3_mp3(second, title="Duplicate ISRC", artist="One Artist", isrc="ISRC-DUPE-001")

    result = reconcile_mp3_library(conn, mp3_root=tmp_path / "dj", dry_run=False)

    count = conn.execute(
        "SELECT COUNT(*) FROM mp3_asset WHERE identity_id = ?",
        (identity_id,),
    ).fetchone()[0]
    assert result.linked == 2
    assert result.skipped_existing == 0
    assert count == 2


def test_reconcile_is_idempotent(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)

    identity_id = _insert_identity(
        conn,
        title="Idempotent",
        artist="Artist",
        isrc="ISRC-IDEMP-001",
    )
    _attach_master_asset(conn, identity_id=identity_id, flac_path="/master/idempotent.flac")

    mp3_file = tmp_path / "dj" / "idempotent.mp3"
    _write_id3_mp3(mp3_file, title="Idempotent", artist="Artist", isrc="ISRC-IDEMP-001")

    first = reconcile_mp3_library(conn, mp3_root=tmp_path / "dj", dry_run=False)
    first_count = conn.execute("SELECT COUNT(*) FROM mp3_asset").fetchone()[0]

    second = reconcile_mp3_library(conn, mp3_root=tmp_path / "dj", dry_run=False)
    second_count = conn.execute("SELECT COUNT(*) FROM mp3_asset").fetchone()[0]

    assert first.linked == 1
    assert first_count == 1
    assert second.linked == 0
    assert second.skipped_existing == 1
    assert second_count == first_count
