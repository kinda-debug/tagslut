from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tagslut.dj.reconcile.lexicon_backfill import run_backfill


def _make_v3_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE track_identity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            beatport_id TEXT,
            spotify_id TEXT,
            artist_norm TEXT,
            title_norm TEXT,
            canonical_bpm REAL,
            canonical_key TEXT,
            canonical_payload_json TEXT,
            lexicon_track_id INTEGER,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE reconcile_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            event_time TEXT,
            source TEXT NOT NULL,
            action TEXT NOT NULL,
            confidence TEXT,
            mp3_path TEXT,
            identity_id INTEGER,
            lexicon_track_id INTEGER,
            details_json TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _make_lexicon_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE Track (
            id INTEGER PRIMARY KEY,
            title TEXT,
            artist TEXT,
            bpm REAL,
            key TEXT,
            energy INTEGER,
            danceability INTEGER,
            happiness INTEGER,
            popularity INTEGER,
            streamingService TEXT,
            streamingId TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE Tempomarker (
            trackId INTEGER,
            startTime REAL,
            bpm REAL
        )
        """
    )
    conn.commit()
    conn.close()


def test_backfill_first_run_sets_canonical_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "music_v3.db"
    lex_path = tmp_path / "lexicon.db"
    _make_v3_db(db_path)
    _make_lexicon_db(lex_path)

    v3 = sqlite3.connect(str(db_path))
    v3.execute(
        """
        INSERT INTO track_identity (beatport_id, artist_norm, title_norm, canonical_payload_json)
        VALUES (?, ?, ?, ?)
        """,
        ("bp-101", "Artist A", "Track A", None),
    )
    v3.commit()
    v3.close()

    lex = sqlite3.connect(str(lex_path))
    lex.execute(
        """
        INSERT INTO Track
          (id, title, artist, bpm, key, energy, danceability, happiness, popularity, streamingService, streamingId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (101, "Track A", "Artist A", 126.0, "8A", 8, 7, 6, 9, "beatport", "bp-101"),
    )
    lex.execute(
        "INSERT INTO Tempomarker (trackId, startTime, bpm) VALUES (?, ?, ?)",
        (101, 0.0, 126.0),
    )
    lex.commit()
    lex.close()

    run_backfill(db_path=db_path, lex_path=lex_path, run_id="run-1", dry_run=False)

    v3 = sqlite3.connect(str(db_path))
    row = v3.execute(
        "SELECT canonical_payload_json, lexicon_track_id FROM track_identity"
    ).fetchone()
    v3.close()

    payload = json.loads(row[0])
    assert payload["lexicon_track_id"] == 101
    assert payload["lexicon_energy"] == 8
    assert payload["lexicon_danceability"] == 7
    assert row[1] == 101


def test_backfill_second_run_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "music_v3.db"
    lex_path = tmp_path / "lexicon.db"
    _make_v3_db(db_path)
    _make_lexicon_db(lex_path)

    v3 = sqlite3.connect(str(db_path))
    v3.execute(
        """
        INSERT INTO track_identity (beatport_id, artist_norm, title_norm, canonical_payload_json)
        VALUES (?, ?, ?, ?)
        """,
        ("bp-202", "Artist B", "Track B", None),
    )
    v3.commit()
    v3.close()

    lex = sqlite3.connect(str(lex_path))
    lex.execute(
        """
        INSERT INTO Track
          (id, title, artist, bpm, key, energy, danceability, happiness, popularity, streamingService, streamingId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (202, "Track B", "Artist B", 128.0, "9A", 5, 6, 5, 6, "beatport", "bp-202"),
    )
    lex.commit()
    lex.close()

    run_backfill(db_path=db_path, lex_path=lex_path, run_id="run-a", dry_run=False)

    v3 = sqlite3.connect(str(db_path))
    first_payload, first_lex_id = v3.execute(
        "SELECT canonical_payload_json, lexicon_track_id FROM track_identity"
    ).fetchone()
    first_identity_count = v3.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0]
    v3.close()

    run_backfill(db_path=db_path, lex_path=lex_path, run_id="run-b", dry_run=False)

    v3 = sqlite3.connect(str(db_path))
    second_payload, second_lex_id = v3.execute(
        "SELECT canonical_payload_json, lexicon_track_id FROM track_identity"
    ).fetchone()
    second_identity_count = v3.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0]
    v3.close()

    assert first_identity_count == 1
    assert second_identity_count == first_identity_count
    assert second_payload == first_payload
    assert second_lex_id == first_lex_id


def test_backfill_unmatched_track_not_modified(tmp_path: Path) -> None:
    db_path = tmp_path / "music_v3.db"
    lex_path = tmp_path / "lexicon.db"
    _make_v3_db(db_path)
    _make_lexicon_db(lex_path)

    v3 = sqlite3.connect(str(db_path))
    v3.execute(
        """
        INSERT INTO track_identity (beatport_id, artist_norm, title_norm, canonical_payload_json)
        VALUES (?, ?, ?, ?)
        """,
        (None, "No Match Artist", "No Match Title", '{"existing": true}'),
    )
    v3.commit()
    v3.close()

    lex = sqlite3.connect(str(lex_path))
    lex.execute(
        """
        INSERT INTO Track
          (id, title, artist, bpm, key, energy, danceability, happiness, popularity, streamingService, streamingId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (303, "Different", "Someone Else", 120.0, "7A", 7, 7, 7, 7, "beatport", "bp-303"),
    )
    lex.commit()
    lex.close()

    run_backfill(db_path=db_path, lex_path=lex_path, run_id="run-unmatched", dry_run=False)

    v3 = sqlite3.connect(str(db_path))
    payload = v3.execute("SELECT canonical_payload_json FROM track_identity").fetchone()[0]
    v3.close()

    assert payload == '{"existing": true}'


def test_backfill_partial_match_flag_set(tmp_path: Path) -> None:
    db_path = tmp_path / "music_v3.db"
    lex_path = tmp_path / "lexicon.db"
    _make_v3_db(db_path)
    _make_lexicon_db(lex_path)

    v3 = sqlite3.connect(str(db_path))
    v3.execute(
        """
        INSERT INTO track_identity (beatport_id, artist_norm, title_norm, canonical_payload_json)
        VALUES (?, ?, ?, ?)
        """,
        (None, "Partial Artist", "Partial Title", None),
    )
    identity_id = v3.execute("SELECT id FROM track_identity").fetchone()[0]
    v3.commit()
    v3.close()

    lex = sqlite3.connect(str(lex_path))
    lex.execute(
        """
        INSERT INTO Track
          (id, title, artist, bpm, key, energy, danceability, happiness, popularity, streamingService, streamingId)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (404, "Partial Title", "Partial Artist", None, None, 0, 0, 0, 0, None, None),
    )
    lex.commit()
    lex.close()

    run_backfill(db_path=db_path, lex_path=lex_path, run_id="run-partial", dry_run=False)

    v3 = sqlite3.connect(str(db_path))
    row = v3.execute(
        "SELECT confidence, details_json FROM reconcile_log WHERE identity_id = ? AND action = 'backfill_metadata'",
        (identity_id,),
    ).fetchone()
    v3.close()

    assert row is not None
    assert row[0] == "low"
    details = json.loads(row[1])
    assert details["method"] == "text"
