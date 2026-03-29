"""Tests for import_lexicon_playlists()."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tagslut.exec.lexicon_import import import_lexicon_playlists, _should_import_playlist


# ---------------------------------------------------------------------------
# Minimal schemas
# ---------------------------------------------------------------------------

_TAGSLUT_DDL = """
CREATE TABLE IF NOT EXISTS track_identity (
    id INTEGER PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,
    artist_norm TEXT,
    title_norm TEXT,
    canonical_title TEXT,
    canonical_artist TEXT,
    source TEXT,
    status TEXT,
    merged_into_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mp3_asset (
    id INTEGER PRIMARY KEY,
    identity_id INTEGER,
    path TEXT NOT NULL UNIQUE,
    lexicon_track_id INTEGER,
    status TEXT NOT NULL DEFAULT 'unverified',
    source TEXT NOT NULL DEFAULT 'unknown',
    profile TEXT NOT NULL DEFAULT 'standard',
    zone TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dj_admission (
    id INTEGER PRIMARY KEY,
    identity_id INTEGER NOT NULL UNIQUE,
    mp3_asset_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    source TEXT NOT NULL DEFAULT 'unknown',
    notes TEXT,
    admitted_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dj_playlist (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    parent_id INTEGER,
    lexicon_playlist_id INTEGER,
    sort_key TEXT,
    playlist_type TEXT NOT NULL DEFAULT 'standard',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dj_playlist_track (
    playlist_id INTEGER NOT NULL,
    dj_admission_id INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, dj_admission_id)
);
CREATE TABLE IF NOT EXISTS reconcile_log (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence TEXT,
    mp3_path TEXT,
    identity_id INTEGER,
    lexicon_track_id INTEGER,
    details_json TEXT
);
"""

_LEX_DDL = """
CREATE TABLE IF NOT EXISTS PlaylistNode (
    id INTEGER PRIMARY KEY,
    name TEXT,
    type INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS PlaylistItem (
    id INTEGER PRIMARY KEY,
    playlistId INTEGER,
    trackId INTEGER,
    position INTEGER
);
CREATE TABLE IF NOT EXISTS Track (
    id INTEGER PRIMARY KEY,
    title TEXT,
    artist TEXT,
    location TEXT,
    archived INTEGER DEFAULT 0,
    incoming INTEGER DEFAULT 0
);
"""

RUN_ID = "test-playlists-001"


def _make_tagslut_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_TAGSLUT_DDL)
    return conn


def _make_lex_db(tmp_path: Path) -> Path:
    lex_path = tmp_path / "lexicon_pl.db"
    conn = sqlite3.connect(str(lex_path))
    conn.executescript(_LEX_DDL)
    conn.close()
    return lex_path


def _lex_add_playlist(lex_path: Path, name: str, pl_type: int = 0) -> int:
    conn = sqlite3.connect(str(lex_path))
    conn.execute("INSERT INTO PlaylistNode (name, type) VALUES (?, ?)", (name, pl_type))
    conn.commit()
    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return pid


def _lex_add_track(lex_path: Path, location: str) -> int:
    conn = sqlite3.connect(str(lex_path))
    conn.execute(
        "INSERT INTO Track (title, artist, location, archived, incoming) VALUES ('T','A',?,0,0)",
        (location,),
    )
    conn.commit()
    tid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return tid


def _lex_add_playlist_item(lex_path: Path, playlist_id: int, track_id: int, position: int) -> None:
    conn = sqlite3.connect(str(lex_path))
    conn.execute(
        "INSERT INTO PlaylistItem (playlistId, trackId, position) VALUES (?, ?, ?)",
        (playlist_id, track_id, position),
    )
    conn.commit()
    conn.close()


def _seed_identity_and_mp3(conn: sqlite3.Connection, lex_path: Path,
                             location: str, key: str) -> tuple[int, int]:
    """Seed track_identity + mp3_asset + link lexicon_track_id. Returns (iid, lex_track_id)."""
    conn.execute(
        "INSERT INTO track_identity (identity_key, artist_norm, title_norm) VALUES (?, 'a', 't')",
        (key,),
    )
    conn.commit()
    iid = conn.execute("SELECT id FROM track_identity WHERE identity_key = ?", (key,)).fetchone()[0]

    lex_tid = _lex_add_track(lex_path, location)
    conn.execute(
        "INSERT INTO mp3_asset (identity_id, path, lexicon_track_id) VALUES (?, ?, ?)",
        (iid, location, lex_tid),
    )
    conn.commit()
    return iid, lex_tid


# ---------------------------------------------------------------------------
# Unit tests for skip-list logic (no DB needed)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,expected_import", [
    ("tagged_lexicon", True),
    ("lexicon_manual_pool", True),
    ("happy", True),
    ("HAPPY_FROM_CSV_plus2", True),
    ("dj-This Is Kölsch-Summer 2024", True),
    ("Duplicate Tracks Summer", True),
    ("fucked", True),
    # Should be skipped
    ("Unnamed Playlist", False),
    ("lexicon_missing_tracks", False),
    ("velocity_dj_session", False),
    ("no bpm", False),
    ("diff", False),
    ("ok", False),
    ("e", False),
    ("done", False),
    ("ROOT", False),
    ("Dump", False),
    ("Lexicon", False),
    ("playlist", False),
    ("Lexicon_tagged_tracks", False),
    ("roon-tidal-whatever", False),
    ("lexicon-since-2025", False),
    ("lexicon-tagged-batch_01", False),
    ("Text Matched Tracks", False),
])
def test_should_import_playlist_skiplist(name: str, expected_import: bool) -> None:
    result, _ = _should_import_playlist(name, node_type=0, track_count=5)
    assert result == expected_import, f"'{name}' expected import={expected_import}"


def test_skip_folder_nodes() -> None:
    """Folder nodes (type=1) are always skipped."""
    result, _ = _should_import_playlist("tagged_lexicon", node_type=1, track_count=5)
    assert result is False


def test_skip_empty_playlists() -> None:
    """Empty playlists (track_count=0) are always skipped."""
    result, _ = _should_import_playlist("tagged_lexicon", node_type=0, track_count=0)
    assert result is False


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_fucked_tracks_get_needs_review(tmp_path: Path) -> None:
    """'fucked' playlist sets dj_admission.status='needs_review'."""
    conn = _make_tagslut_db()
    lex_path = _make_lex_db(tmp_path)

    loc = "/Volumes/MUSIC/DJ_LIBRARY/bad.mp3"
    iid, _ = _seed_identity_and_mp3(conn, lex_path, loc, "bad_track")

    pl_id = _lex_add_playlist(lex_path, "fucked")
    lex_tid = conn.execute(
        "SELECT lexicon_track_id FROM mp3_asset WHERE path = ?", (loc,)
    ).fetchone()[0]
    _lex_add_playlist_item(lex_path, pl_id, lex_tid, 1)

    import_lexicon_playlists(
        conn,
        lexicon_db_path=lex_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        dry_run=False,
    )

    status = conn.execute(
        "SELECT status FROM dj_admission WHERE identity_id = ?", (iid,)
    ).fetchone()
    assert status is not None
    assert status[0] == "needs_review"


def test_duplicate_tracks_gets_is_duplicate_flag(tmp_path: Path) -> None:
    """'Duplicate Tracks ...' playlist appends is_duplicate:true to dj_admission.notes."""
    conn = _make_tagslut_db()
    lex_path = _make_lex_db(tmp_path)

    loc = "/Volumes/MUSIC/DJ_LIBRARY/dup.mp3"
    iid, _ = _seed_identity_and_mp3(conn, lex_path, loc, "dup_track")

    pl_id = _lex_add_playlist(lex_path, "Duplicate Tracks Summer 2024")
    lex_tid = conn.execute(
        "SELECT lexicon_track_id FROM mp3_asset WHERE path = ?", (loc,)
    ).fetchone()[0]
    _lex_add_playlist_item(lex_path, pl_id, lex_tid, 1)

    import_lexicon_playlists(
        conn,
        lexicon_db_path=lex_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        dry_run=False,
    )

    notes = conn.execute(
        "SELECT notes FROM dj_admission WHERE identity_id = ?", (iid,)
    ).fetchone()
    assert notes is not None
    assert "is_duplicate:true" in (notes[0] or "")


def test_ordinal_preserved(tmp_path: Path) -> None:
    """Ordinal from Lexicon position is preserved in dj_playlist_track."""
    conn = _make_tagslut_db()
    lex_path = _make_lex_db(tmp_path)

    pl_id = _lex_add_playlist(lex_path, "tagged_lexicon")

    for i, loc in enumerate([
        "/Volumes/MUSIC/DJ_LIBRARY/t1.mp3",
        "/Volumes/MUSIC/DJ_LIBRARY/t2.mp3",
        "/Volumes/MUSIC/DJ_LIBRARY/t3.mp3",
    ], start=1):
        iid, _ = _seed_identity_and_mp3(conn, lex_path, loc, f"ord_track_{i}")
        lex_tid = conn.execute(
            "SELECT lexicon_track_id FROM mp3_asset WHERE path = ?", (loc,)
        ).fetchone()[0]
        _lex_add_playlist_item(lex_path, pl_id, lex_tid, i * 10)

    import_lexicon_playlists(
        conn,
        lexicon_db_path=lex_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        dry_run=False,
    )

    db_pl = conn.execute("SELECT id FROM dj_playlist WHERE name = 'tagged_lexicon'").fetchone()
    assert db_pl is not None

    ordinals = conn.execute(
        "SELECT ordinal FROM dj_playlist_track WHERE playlist_id = ? ORDER BY ordinal",
        (db_pl[0],),
    ).fetchall()
    assert [r[0] for r in ordinals] == [10, 20, 30]


def test_idempotent_double_run(tmp_path: Path) -> None:
    """Running import twice produces the same result (idempotent)."""
    conn = _make_tagslut_db()
    lex_path = _make_lex_db(tmp_path)

    pl_id = _lex_add_playlist(lex_path, "happy")
    loc = "/Volumes/MUSIC/DJ_LIBRARY/happy.mp3"
    iid, _ = _seed_identity_and_mp3(conn, lex_path, loc, "happy_track")
    lex_tid = conn.execute(
        "SELECT lexicon_track_id FROM mp3_asset WHERE path = ?", (loc,)
    ).fetchone()[0]
    _lex_add_playlist_item(lex_path, pl_id, lex_tid, 1)

    kwargs = dict(
        lexicon_db_path=lex_path, run_id=RUN_ID,
        log_dir=tmp_path / "logs", dry_run=False,
    )
    import_lexicon_playlists(conn, **kwargs)
    import_lexicon_playlists(conn, **kwargs)

    pl_count = conn.execute(
        "SELECT COUNT(*) FROM dj_playlist WHERE name = 'happy'"
    ).fetchone()[0]
    pt_count = conn.execute(
        "SELECT COUNT(*) FROM dj_playlist_track"
    ).fetchone()[0]
    assert pl_count == 1
    assert pt_count == 1
