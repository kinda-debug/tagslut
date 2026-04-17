"""Tests for import_lexicon_metadata()."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import zipfile

import pytest

from tagslut.exec.lexicon_import import import_lexicon_metadata


# ---------------------------------------------------------------------------
# Minimal schemas
# ---------------------------------------------------------------------------

_TAGSLUT_DDL = """
CREATE TABLE IF NOT EXISTS track_identity (
    id INTEGER PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,
    isrc TEXT,
    artist_norm TEXT,
    title_norm TEXT,
    canonical_title TEXT,
    canonical_artist TEXT,
    canonical_bpm REAL,
    canonical_key TEXT,
    canonical_genre TEXT,
    canonical_label TEXT,
    canonical_mix_name TEXT,
    canonical_payload_json TEXT,
    spotify_id TEXT,
    beatport_id TEXT,
    tidal_id TEXT,
    qobuz_id TEXT,
    apple_music_id TEXT,
    deezer_id TEXT,
    traxsource_id TEXT,
    itunes_id TEXT,
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
    bitrate INTEGER,
    sample_rate INTEGER,
    duration_s REAL,
    content_sha256 TEXT,
    reconciled_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS dj_track_profile (
    identity_id INTEGER PRIMARY KEY,
    rating INTEGER,
    energy INTEGER,
    set_role TEXT,
    dj_tags_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    last_played_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
CREATE TABLE IF NOT EXISTS Track (
    id INTEGER PRIMARY KEY,
    title TEXT,
    artist TEXT,
    location TEXT,
    locationUnique TEXT,
    bpm REAL,
    key TEXT,
    energy INTEGER,
    rating INTEGER,
    lastPlayed TEXT,
    color TEXT,
    genre TEXT,
    label TEXT,
    remixer TEXT,
    extra1 TEXT,
    extra2 TEXT,
    data TEXT,
    fingerprint TEXT,
    importSource TEXT,
    streamingService TEXT,
    streamingId TEXT,
    archived INTEGER DEFAULT 0,
    incoming INTEGER DEFAULT 0
);
"""

RUN_ID = "test-lex-001"


def _make_tagslut_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_TAGSLUT_DDL)
    return conn


def _make_lex_db(tmp_path: Path) -> Path:
    lex_path = tmp_path / "lexicon.db"
    conn = sqlite3.connect(str(lex_path))
    conn.executescript(_LEX_DDL)
    conn.close()
    return lex_path


def _seed_tagslut_identity(conn: sqlite3.Connection, *, key: str, artist_norm: str,
                            title_norm: str, **kwargs) -> int:
    cols = ["identity_key", "artist_norm", "title_norm"] + list(kwargs.keys())
    vals = [key, artist_norm, title_norm] + list(kwargs.values())
    placeholders = ", ".join("?" * len(vals))
    conn.execute(
        f"INSERT INTO track_identity ({', '.join(cols)}) VALUES ({placeholders})",
        vals,
    )
    conn.commit()
    return conn.execute("SELECT id FROM track_identity WHERE identity_key = ?", (key,)).fetchone()[0]


def _seed_mp3_asset(conn: sqlite3.Connection, *, identity_id: int, path: str) -> int:
    conn.execute(
        "INSERT INTO mp3_asset (identity_id, path) VALUES (?, ?)", (identity_id, path)
    )
    conn.commit()
    return conn.execute("SELECT id FROM mp3_asset WHERE path = ?", (path,)).fetchone()[0]


def _seed_profile(conn: sqlite3.Connection, *, identity_id: int, **kwargs) -> None:
    cols = ["identity_id"] + list(kwargs.keys())
    vals = [identity_id] + list(kwargs.values())
    placeholders = ", ".join("?" * len(vals))
    conn.execute(
        f"INSERT INTO dj_track_profile ({', '.join(cols)}) VALUES ({placeholders})",
        vals,
    )
    conn.commit()


def _insert_lex_track(lex_path: Path, *, location: str, **kwargs) -> int:
    conn = sqlite3.connect(str(lex_path))
    defaults = dict(
        title=kwargs.get("title", "Test Title"),
        artist=kwargs.get("artist", "Test Artist"),
        location=location,
        locationUnique=kwargs.get("locationUnique", None),
        bpm=kwargs.get("bpm", 128),
        key=kwargs.get("key", "Am"),
        energy=kwargs.get("energy", 5),
        rating=kwargs.get("rating", 3),
        lastPlayed=kwargs.get("lastPlayed", None),
        color=kwargs.get("color", None),
        genre=kwargs.get("genre", None),
        label=kwargs.get("label", None),
        remixer=kwargs.get("remixer", None),
        extra1=kwargs.get("extra1", None),
        extra2=kwargs.get("extra2", None),
        data=kwargs.get("data", None),
        fingerprint=kwargs.get("fingerprint", None),
        importSource=kwargs.get("importSource", None),
        streamingService=kwargs.get("streamingService", None),
        streamingId=kwargs.get("streamingId", None),
        archived=0,
        incoming=0,
    )
    conn.execute(
        """INSERT INTO Track (title, artist, location, locationUnique, bpm, key, energy, rating,
           lastPlayed, color, genre, label, remixer, extra1, extra2, data, fingerprint,
           importSource, streamingService, streamingId, archived, incoming)
           VALUES (:title, :artist, :location, :locationUnique, :bpm, :key, :energy, :rating,
                   :lastPlayed, :color, :genre, :label, :remixer, :extra1, :extra2, :data, :fingerprint,
                   :importSource, :streamingService, :streamingId, :archived, :incoming)""",
        defaults,
    )
    conn.commit()
    row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return row_id


def _zip_lex_db(lex_path: Path, *, name: str = "main.db") -> Path:
    zip_path = lex_path.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(lex_path, arcname=name)
    return zip_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_null_field_written(tmp_path: Path) -> None:
    """NULL canonical_genre → written from Lexicon."""
    conn = _make_tagslut_db()
    loc = "/Volumes/MUSIC/DJ_LIBRARY/test.mp3"
    iid = _seed_tagslut_identity(conn, key="ti1", artist_norm="test artist", title_norm="test title")
    _seed_mp3_asset(conn, identity_id=iid, path=loc)

    lex_path = _make_lex_db(tmp_path)
    _insert_lex_track(lex_path, location=loc, genre="Techno")

    result = import_lexicon_metadata(
        conn,
        lexicon_db_path=lex_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        dry_run=False,
    )
    assert result["fields_written"] >= 1
    genre = conn.execute(
        "SELECT canonical_genre FROM track_identity WHERE id = ?", (iid,)
    ).fetchone()[0]
    assert genre == "Techno"


def test_non_null_field_skipped_without_prefer_lexicon(tmp_path: Path) -> None:
    """Non-null canonical_genre is NOT overwritten without --prefer-lexicon."""
    conn = _make_tagslut_db()
    loc = "/Volumes/MUSIC/DJ_LIBRARY/test2.mp3"
    iid = _seed_tagslut_identity(conn, key="ti2", artist_norm="artist", title_norm="title",
                                  canonical_genre="House")
    _seed_mp3_asset(conn, identity_id=iid, path=loc)

    lex_path = _make_lex_db(tmp_path)
    _insert_lex_track(lex_path, location=loc, genre="Techno")

    import_lexicon_metadata(
        conn,
        lexicon_db_path=lex_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        dry_run=False,
    )

    genre = conn.execute(
        "SELECT canonical_genre FROM track_identity WHERE id = ?", (iid,)
    ).fetchone()[0]
    assert genre == "House"  # Preserved


def test_prefer_lexicon_overwrites(tmp_path: Path) -> None:
    """prefer_lexicon=True → overwrites non-null canonical_genre."""
    conn = _make_tagslut_db()
    loc = "/Volumes/MUSIC/DJ_LIBRARY/test3.mp3"
    iid = _seed_tagslut_identity(conn, key="ti3", artist_norm="artist", title_norm="title",
                                  canonical_genre="House")
    _seed_mp3_asset(conn, identity_id=iid, path=loc)

    lex_path = _make_lex_db(tmp_path)
    _insert_lex_track(lex_path, location=loc, genre="Techno")

    import_lexicon_metadata(
        conn,
        lexicon_db_path=lex_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        prefer_lexicon=True,
        dry_run=False,
    )

    genre = conn.execute(
        "SELECT canonical_genre FROM track_identity WHERE id = ?", (iid,)
    ).fetchone()[0]
    assert genre == "Techno"


def test_dj_tags_json_never_modified(tmp_path: Path) -> None:
    """dj_tags_json MUST NEVER be modified under any condition."""
    conn = _make_tagslut_db()
    loc = "/Volumes/MUSIC/DJ_LIBRARY/test4.mp3"
    iid = _seed_tagslut_identity(conn, key="ti4", artist_norm="artist", title_norm="title")
    _seed_mp3_asset(conn, identity_id=iid, path=loc)
    original_tags = '["tag1","tag2"]'
    _seed_profile(conn, identity_id=iid, dj_tags_json=original_tags, energy=None, rating=None)

    lex_path = _make_lex_db(tmp_path)
    _insert_lex_track(lex_path, location=loc, energy=8, rating=5,
                      extra1="sometag", extra2="anothertag")

    import_lexicon_metadata(
        conn,
        lexicon_db_path=lex_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        prefer_lexicon=True,
        dry_run=False,
    )

    tags_after = conn.execute(
        "SELECT dj_tags_json FROM dj_track_profile WHERE identity_id = ?", (iid,)
    ).fetchone()[0]
    assert tags_after == original_tags, "dj_tags_json was modified — HARD RULE violation"


def test_peak_row_never_touched(tmp_path: Path) -> None:
    """set_role='peak' row survives full import completely unchanged."""
    conn = _make_tagslut_db()
    loc = "/Volumes/MUSIC/DJ_LIBRARY/peak.mp3"
    iid = _seed_tagslut_identity(conn, key="ti5", artist_norm="peak artist", title_norm="peak track")
    _seed_mp3_asset(conn, identity_id=iid, path=loc)
    _seed_profile(conn, identity_id=iid, set_role="peak",
                  energy=10, rating=5, dj_tags_json='["peak"]', notes="peak notes")

    lex_path = _make_lex_db(tmp_path)
    _insert_lex_track(lex_path, location=loc, energy=1, rating=1,
                      label="Override Label", color="red")

    import_lexicon_metadata(
        conn,
        lexicon_db_path=lex_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        prefer_lexicon=True,
        dry_run=False,
    )

    row = conn.execute(
        "SELECT energy, rating, set_role, dj_tags_json, notes FROM dj_track_profile WHERE identity_id = ?",
        (iid,),
    ).fetchone()
    assert row[0] == 10, "energy changed on peak row"
    assert row[1] == 5, "rating changed on peak row"
    assert row[2] == "peak", "set_role changed"
    assert row[3] == '["peak"]', "dj_tags_json changed"
    assert row[4] == "peak notes", "notes changed on peak row"


def test_extra1_extra2_appended_to_notes_not_tags(tmp_path: Path) -> None:
    """extra1/extra2 appended to notes, never to dj_tags_json."""
    conn = _make_tagslut_db()
    loc = "/Volumes/MUSIC/DJ_LIBRARY/extra.mp3"
    iid = _seed_tagslut_identity(conn, key="ti6", artist_norm="artist", title_norm="title")
    _seed_mp3_asset(conn, identity_id=iid, path=loc)
    _seed_profile(conn, identity_id=iid, dj_tags_json='[]', notes="base note")

    lex_path = _make_lex_db(tmp_path)
    _insert_lex_track(lex_path, location=loc, extra1="myextra1", extra2="myextra2")

    import_lexicon_metadata(
        conn,
        lexicon_db_path=lex_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        dry_run=False,
    )

    row = conn.execute(
        "SELECT notes, dj_tags_json FROM dj_track_profile WHERE identity_id = ?", (iid,)
    ).fetchone()
    assert "lexicon_extra1:myextra1" in row[0]
    assert "lexicon_extra2:myextra2" in row[0]
    assert row[1] == "[]"  # dj_tags_json unchanged


def test_idempotent_double_run(tmp_path: Path) -> None:
    """Running import twice produces the same result (idempotent)."""
    conn = _make_tagslut_db()
    loc = "/Volumes/MUSIC/DJ_LIBRARY/idem.mp3"
    iid = _seed_tagslut_identity(conn, key="ti7", artist_norm="idem artist", title_norm="idem title")
    _seed_mp3_asset(conn, identity_id=iid, path=loc)

    lex_path = _make_lex_db(tmp_path)
    _insert_lex_track(lex_path, location=loc, bpm=140.0, key="Gm")

    kwargs = dict(
        lexicon_db_path=lex_path, run_id=RUN_ID,
        log_dir=tmp_path / "logs", dry_run=False,
    )
    import_lexicon_metadata(conn, **kwargs)
    bpm_after_1 = conn.execute(
        "SELECT canonical_bpm FROM track_identity WHERE id = ?", (iid,)
    ).fetchone()[0]

    import_lexicon_metadata(conn, **kwargs)
    bpm_after_2 = conn.execute(
        "SELECT canonical_bpm FROM track_identity WHERE id = ?", (iid,)
    ).fetchone()[0]

    assert bpm_after_1 == bpm_after_2 == 140.0


def test_location_unique_match_preserves_lexicon_payload(tmp_path: Path) -> None:
    conn = _make_tagslut_db()
    actual_path = "/Volumes/MUSIC/DJ_LIBRARY/matched.mp3"
    lex_location = "/Volumes/MUSIC/DJ_LIBRARY/mismatch.mp3"
    iid = _seed_tagslut_identity(
        conn,
        key="ti8",
        artist_norm="different artist",
        title_norm="different title",
    )
    _seed_mp3_asset(conn, identity_id=iid, path=actual_path)

    lex_path = _make_lex_db(tmp_path)
    lex_id = _insert_lex_track(
        lex_path,
        location=lex_location,
        locationUnique=actual_path,
        data='{"itunes":{"trackId":123}}',
        fingerprint="fp-123",
        importSource="7",
    )

    import_lexicon_metadata(
        conn,
        lexicon_db_path=lex_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        dry_run=False,
    )

    mp3_row = conn.execute(
        "SELECT lexicon_track_id FROM mp3_asset WHERE path = ?",
        (actual_path,),
    ).fetchone()
    payload_row = conn.execute(
        "SELECT canonical_payload_json FROM track_identity WHERE id = ?",
        (iid,),
    ).fetchone()
    payload = json.loads(payload_row[0])

    assert mp3_row[0] == lex_id
    assert payload["lexicon_track_id"] == lex_id
    assert payload["lexicon_location"] == lex_location
    assert payload["lexicon_location_unique"] == actual_path
    assert payload["lexicon_fingerprint"] == "fp-123"
    assert payload["lexicon_import_source"] == "7"
    assert payload["lexicon_source_payload"] == {"itunes": {"trackId": 123}}


def test_backup_zip_supported(tmp_path: Path) -> None:
    conn = _make_tagslut_db()
    loc = "/Volumes/MUSIC/DJ_LIBRARY/zipped.mp3"
    iid = _seed_tagslut_identity(conn, key="ti9", artist_norm="zip artist", title_norm="zip title")
    _seed_mp3_asset(conn, identity_id=iid, path=loc)

    lex_path = _make_lex_db(tmp_path)
    _insert_lex_track(lex_path, location=loc, genre="Electro")
    zip_path = _zip_lex_db(lex_path)

    result = import_lexicon_metadata(
        conn,
        lexicon_db_path=zip_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        dry_run=False,
    )

    genre = conn.execute(
        "SELECT canonical_genre FROM track_identity WHERE id = ?",
        (iid,),
    ).fetchone()[0]
    assert result["matched"] == 1
    assert genre == "Electro"
