from __future__ import annotations

import sqlite3
from pathlib import Path

from tagslut.storage.schema import init_db
from tagslut.storage.v3.backfill_identity import BackfillConfig, backfill_v3_identity_links


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
        """
        INSERT INTO track_identity (
            identity_key,
            artist_norm,
            title_norm
        ) VALUES (?, ?, ?)
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
        """
        INSERT INTO track_identity (
            identity_key,
            isrc,
            artist_norm,
            title_norm,
            duration_ref_ms
        ) VALUES (?, ?, ?, ?, ?)
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
            '{"artist":"I Can Lick Any Sonofabitch in the House","title":"Dead By Christmas Time","album":"Mayberry","isrc":"USCGJ1349317"}',
            195827,
        ),
    )
    conn.executemany(
        """
        INSERT INTO track_identity (
            identity_key,
            isrc,
            artist_norm,
            title_norm,
            duration_ref_ms
        ) VALUES (?, ?, ?, ?, ?)
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
