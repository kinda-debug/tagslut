from __future__ import annotations

import sqlite3
from pathlib import Path

from tagslut.metadata.models.types import MatchConfidence, ProviderTrack
from tagslut.metadata.store.db_writer import _upsert_library_track_source
from tagslut.storage.schema import init_db
from tagslut.storage.v3.backfill_identity import BackfillConfig, backfill_v3_identity_links
from tests.conftest import PROV_COLS, PROV_VALS


def test_backfill_reuses_existing_identity_by_identity_key(tmp_path: Path) -> None:
    db_path = tmp_path / "backfill.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """
        INSERT INTO files (
            path,
            duration,
            metadata_json
        ) VALUES (?, ?, ?)
        """,
        (
            "/music/johnny-utah-nvrllyrlly.flac",
            144.242,
            '{"artist":"Johnny Utah","title":"Nvrllyrlly","album":"Johnny Utah"}',
        ),
    )
    conn.execute(
        f"""
        INSERT INTO track_identity (
            identity_key,
            artist_norm,
            title_norm{PROV_COLS}
        ) VALUES (?, ?, ?{PROV_VALS})
        """,
        (
            "text:johnny utah|nvrllyrlly",
            "johnny utah",
            "nvrllyrlly",
        ),
    )
    conn.commit()

    summary = backfill_v3_identity_links(
        conn,
        db_path=db_path,
        config=BackfillConfig(
            execute=True,
            resume_from_file_id=0,
            commit_every=500,
            checkpoint_every=500,
            busy_timeout_ms=10_000,
            abort_error_rate_per_1000=50.0,
            artifacts_dir=tmp_path / "artifacts",
            limit=None,
            verbose=False,
        ),
    )

    identity_count = conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0]
    active_link = conn.execute(
        """
        SELECT al.identity_id
        FROM asset_link al
        JOIN asset_file af ON af.id = al.asset_id
        WHERE af.path = ? AND al.active = 1
        """,
        ("/music/johnny-utah-nvrllyrlly.flac",),
    ).fetchone()
    conn.close()

    assert summary["errors"] == 0
    assert summary["created"] == 0
    assert summary["reused"] == 1
    assert identity_count == 1
    assert active_link is not None
    assert int(active_link[0]) == 1


def test_backfill_reuses_best_match_for_duplicate_isrc_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "backfill_isrc.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """
        INSERT INTO files (
            path,
            canonical_artist,
            canonical_title,
            canonical_isrc,
            duration_ref_ms
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            "/music/bon-iver-holocene.flac",
            "Bon Iver",
            "Holocene",
            "US38Y1113503",
            321000,
        ),
    )
    conn.executemany(
        f"""
        INSERT INTO track_identity (
            identity_key,
            isrc,
            artist_norm,
            title_norm,
            duration_ref_ms{PROV_COLS}
        ) VALUES (?, ?, ?, ?, ?{PROV_VALS})
        """,
        [
            ("isrc:US38Y1113503", "US38Y1113503", None, None, None),
            ("isrc:us38y1113503-dup", "US38Y1113503", "bon iver", "holocene", 321000),
        ],
    )
    conn.commit()

    summary = backfill_v3_identity_links(
        conn,
        db_path=db_path,
        config=BackfillConfig(
            execute=True,
            resume_from_file_id=0,
            commit_every=500,
            checkpoint_every=500,
            busy_timeout_ms=10_000,
            abort_error_rate_per_1000=50.0,
            artifacts_dir=tmp_path / "artifacts",
            limit=None,
            verbose=False,
        ),
    )

    active_link = conn.execute(
        """
        SELECT al.identity_id
        FROM asset_link al
        JOIN asset_file af ON af.id = al.asset_id
        WHERE af.path = ? AND al.active = 1
        """,
        ("/music/bon-iver-holocene.flac",),
    ).fetchone()
    conn.close()

    assert summary["errors"] == 0
    assert summary["conflicted"] == 0
    assert summary["reused"] == 1
    assert active_link is not None
    assert int(active_link[0]) == 2


def test_backfill_reuses_exact_identity_over_equivalent_text_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "backfill_fuzzy.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.execute(
        """
        INSERT INTO files (
            path,
            metadata_json,
            duration_ref_ms
        ) VALUES (?, ?, ?)
        """,
        (
            "/music/dead-by-christmas-time.flac",
            (
                '{"artist":"I Can Lick Any Sonofabitch in the House",'
                '"title":"Dead By Christmas Time","album":"Mayberry",'
                '"isrc":"USCGJ1349317"}'
            ),
            195827,
        ),
    )
    conn.executemany(
        f"""
        INSERT INTO track_identity (
            identity_key,
            isrc,
            artist_norm,
            title_norm,
            duration_ref_ms{PROV_COLS}
        ) VALUES (?, ?, ?, ?, ?{PROV_VALS})
        """,
        [
            (
                "isrc:uscgj1349317",
                "USCGJ1349317",
                "i can lick any sonofabitch in the house",
                "dead by christmas time",
                195827,
            ),
            (
                "text:i can lick any sonofabitch in the house|dead by christmas time",
                None,
                "i can lick any sonofabitch in the house",
                "dead by christmas time",
                195827,
            ),
        ],
    )
    conn.commit()

    summary = backfill_v3_identity_links(
        conn,
        db_path=db_path,
        config=BackfillConfig(
            execute=True,
            resume_from_file_id=0,
            commit_every=500,
            checkpoint_every=500,
            busy_timeout_ms=10_000,
            abort_error_rate_per_1000=50.0,
            artifacts_dir=tmp_path / "artifacts",
            limit=None,
            verbose=False,
        ),
    )

    active_link = conn.execute(
        """
        SELECT al.identity_id
        FROM asset_link al
        JOIN asset_file af ON af.id = al.asset_id
        WHERE af.path = ? AND al.active = 1
        """,
        ("/music/dead-by-christmas-time.flac",),
    ).fetchone()
    conn.close()

    assert summary["errors"] == 0
    assert summary["conflicted"] == 0
    assert summary["fuzzy_near_collision"] == 0
    assert summary["reused"] == 1
    assert active_link is not None
    assert int(active_link[0]) == 1


def test_library_track_source_write_supports_legacy_schema() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE library_track_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_track_key TEXT,
            service TEXT,
            service_track_id TEXT,
            url TEXT,
            metadata_json TEXT,
            duration_ms INTEGER,
            isrc TEXT,
            album_art_url TEXT,
            genre TEXT,
            bpm REAL,
            musical_key TEXT,
            album_title TEXT,
            artist_name TEXT,
            track_number INTEGER,
            disc_number INTEGER,
            match_confidence TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    match = ProviderTrack(
        service="beatport",
        service_track_id="bp-1",
        url="https://beatport.example/track/bp-1",
        duration_ms=123000,
        genre="Tech House",
        bpm=128.0,
        key="Am",
        match_confidence=MatchConfidence.EXACT,
        raw={"id": "bp-1"},
    )

    _upsert_library_track_source(conn, "library_track_key", "library:key", match)

    row = conn.execute(
        "SELECT service, service_track_id, url, metadata_json FROM library_track_sources"
    ).fetchone()
    conn.close()

    assert row == (
        "beatport",
        "bp-1",
        "https://beatport.example/track/bp-1",
        '{"id": "bp-1"}',
    )


def test_library_track_source_write_supports_v3_schema() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE library_track_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identity_key TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_track_id TEXT NOT NULL,
            source_url TEXT,
            match_confidence TEXT,
            raw_payload_json TEXT,
            metadata_json TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    match = ProviderTrack(
        service="tidal",
        service_track_id="td-1",
        url="https://tidal.example/track/td-1",
        match_confidence=MatchConfidence.STRONG,
        raw={"id": "td-1"},
    )

    _upsert_library_track_source(conn, "identity_key", "identity:key", match)

    row = conn.execute(
        "SELECT identity_key, provider, provider_track_id, source_url, raw_payload_json, metadata_json FROM library_track_sources"
    ).fetchone()
    conn.close()

    assert row == (
        "identity:key",
        "tidal",
        "td-1",
        "https://tidal.example/track/td-1",
        '{"id": "td-1"}',
        '{"id": "td-1"}',
    )
