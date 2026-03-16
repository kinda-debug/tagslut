from __future__ import annotations

import sqlite3

import pytest

from tagslut.storage.schema import init_db
from tagslut.storage.v3.dual_write import dual_write_registered_file
from tagslut.storage.v3.identity_service import resolve_or_create_identity
from tagslut.storage.v3.merge_identities import merge_group_by_repointing_assets
from tagslut.storage.v3.schema import create_schema_v3


def _trace_has_sql(trace: list[str], needle: str) -> bool:
    needle_upper = needle.upper()
    return any(needle_upper in str(stmt).upper() for stmt in trace)


def _trace_has_exact_statement(trace: list[str], statement: str) -> bool:
    statement_upper = statement.upper()
    return any(str(stmt).strip().upper() == statement_upper for stmt in trace)


def test_dual_write_registered_file_rolls_back_when_flow_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "phase1.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("tagslut.storage.v3.dual_write.record_provenance_event", _boom)

    with pytest.raises(RuntimeError, match="boom"):
        dual_write_registered_file(
            conn,
            path="/music/test.flac",
            content_sha256="abc123",
            streaminfo_md5="def456",
            checksum="abc123",
            size_bytes=1234,
            mtime=100.0,
            duration_s=300.0,
            sample_rate=44100,
            bit_depth=16,
            bitrate=900,
            library="default",
            zone="staging",
            download_source="bpdl",
            download_date="2026-02-09T00:00:00Z",
            mgmt_status="new",
            metadata={"ISRC": "US1234567890", "artist": "Example", "title": "Track"},
            duration_ref_ms=300000,
            duration_ref_source="beatport",
            event_time="2026-02-09T00:00:00Z",
        )

    assert conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM asset_link").fetchone()[0] == 0
    conn.close()


def test_dual_write_registered_file_does_not_manage_outer_transaction_success() -> None:
    conn = sqlite3.connect(":memory:")
    trace: list[str] = []
    conn.set_trace_callback(trace.append)
    init_db(conn)

    trace.clear()
    conn.execute("BEGIN")
    dual_write_registered_file(
        conn,
        path="/music/test.flac",
        content_sha256="abc123",
        streaminfo_md5="def456",
        checksum="abc123",
        size_bytes=1234,
        mtime=100.0,
        duration_s=300.0,
        sample_rate=44100,
        bit_depth=16,
        bitrate=900,
        library="default",
        zone="staging",
        download_source="bpdl",
        download_date="2026-02-09T00:00:00Z",
        mgmt_status="new",
        metadata={"ISRC": "US1234567890", "artist": "Example", "title": "Track"},
        duration_ref_ms=300000,
        duration_ref_source="beatport",
        event_time="2026-02-09T00:00:00Z",
    )

    assert conn.in_transaction is True
    assert not _trace_has_sql(trace, "BEGIN IMMEDIATE")
    assert not _trace_has_exact_statement(trace, "COMMIT")
    assert not _trace_has_exact_statement(trace, "ROLLBACK")
    assert conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM asset_link").fetchone()[0] == 1

    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM asset_link").fetchone()[0] == 0
    conn.close()


def test_dual_write_registered_file_does_not_manage_outer_transaction_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = sqlite3.connect(":memory:")
    trace: list[str] = []
    conn.set_trace_callback(trace.append)
    init_db(conn)

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("tagslut.storage.v3.dual_write.record_provenance_event", _boom)

    trace.clear()
    conn.execute("BEGIN")
    with pytest.raises(RuntimeError, match="boom"):
        dual_write_registered_file(
            conn,
            path="/music/test.flac",
            content_sha256="abc123",
            streaminfo_md5="def456",
            checksum="abc123",
            size_bytes=1234,
            mtime=100.0,
            duration_s=300.0,
            sample_rate=44100,
            bit_depth=16,
            bitrate=900,
            library="default",
            zone="staging",
            download_source="bpdl",
            download_date="2026-02-09T00:00:00Z",
            mgmt_status="new",
            metadata={"ISRC": "US1234567890", "artist": "Example", "title": "Track"},
            duration_ref_ms=300000,
            duration_ref_source="beatport",
            event_time="2026-02-09T00:00:00Z",
        )

    assert conn.in_transaction is True
    assert not _trace_has_sql(trace, "BEGIN IMMEDIATE")
    assert not _trace_has_exact_statement(trace, "COMMIT")
    assert not _trace_has_exact_statement(trace, "ROLLBACK")
    assert conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM asset_link").fetchone()[0] == 1

    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM asset_link").fetchone()[0] == 0
    conn.close()


def test_resolve_or_create_identity_does_not_manage_outer_transaction_success() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    trace: list[str] = []
    conn.set_trace_callback(trace.append)
    create_schema_v3(conn)
    init_db(conn)

    trace.clear()
    conn.execute("BEGIN")
    identity_id = resolve_or_create_identity(
        conn,
        asset_row={"path": "/music/new.flac", "duration_s": 300.0},
        metadata={"isrc": "ABC123", "artist": "Artist", "title": "Track"},
        provenance={"source": "tidal"},
    )
    assert identity_id is not None

    assert conn.in_transaction is True
    assert not _trace_has_sql(trace, "BEGIN IMMEDIATE")
    assert not _trace_has_exact_statement(trace, "COMMIT")
    assert not _trace_has_exact_statement(trace, "ROLLBACK")
    assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 1

    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 0
    conn.close()


def test_resolve_or_create_identity_does_not_manage_outer_transaction_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tagslut.storage.v3.identity_service as identity_mod

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    trace: list[str] = []
    conn.set_trace_callback(trace.append)
    create_schema_v3(conn)
    init_db(conn)

    def _create_then_boom(_conn: sqlite3.Connection, _asset_row: sqlite3.Row, _fields):
        _conn.execute(
            "INSERT INTO track_identity (identity_key, isrc) VALUES (?, ?)",
            ("isrc:abc123", "ABC123"),
        )
        raise RuntimeError("boom-after-insert")

    monkeypatch.setattr(identity_mod, "_create_identity", _create_then_boom)

    trace.clear()
    conn.execute("BEGIN")
    with pytest.raises(RuntimeError, match="boom-after-insert"):
        resolve_or_create_identity(
            conn,
            asset_row={"path": "/music/new.flac", "duration_s": 300.0},
            metadata={"isrc": "ABC123", "artist": "Artist", "title": "Track"},
            provenance={"source": "tidal"},
        )

    assert conn.in_transaction is True
    assert not _trace_has_sql(trace, "BEGIN IMMEDIATE")
    assert not _trace_has_exact_statement(trace, "COMMIT")
    assert not _trace_has_exact_statement(trace, "ROLLBACK")
    assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 1

    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 0
    conn.close()


def _seed_merge_fixture(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO asset_file (id, path) VALUES (?, ?)",
        [
            (1, "/music/a1.flac"),
            (2, "/music/a2.flac"),
        ],
    )
    conn.executemany(
        """
            INSERT INTO track_identity (
                id,
                identity_key,
                beatport_id,
                canonical_artist,
                canonical_title,
                enriched_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
        [
            (1, "beatport:BP-1-a", "BP-1", "Artist A", "Track A", None),
            (2, "beatport:BP-1-b", "BP-2", None, None, "2026-03-04T00:00:00Z"),
        ],
    )
    conn.executemany(
        "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
        [
            (1, 1),
            (2, 2),
        ],
    )
    conn.execute(
        """
        INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version)
        VALUES (1, 1, 1.0, '{}', 1)
        """
    )
    conn.commit()


def test_merge_group_by_repointing_assets_does_not_manage_outer_transaction_success() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    trace: list[str] = []
    conn.set_trace_callback(trace.append)
    create_schema_v3(conn)
    _seed_merge_fixture(conn)

    trace.clear()
    conn.execute("BEGIN")
    merge_group_by_repointing_assets(conn, 2, [1], dry_run=False)

    assert conn.in_transaction is True
    assert not _trace_has_sql(trace, "BEGIN IMMEDIATE")
    assert not _trace_has_exact_statement(trace, "COMMIT")
    assert not _trace_has_exact_statement(trace, "ROLLBACK")

    loser = conn.execute(
        "SELECT beatport_id, merged_into_id FROM track_identity WHERE id = 1"
    ).fetchone()
    assert loser["beatport_id"] is None
    assert int(loser["merged_into_id"]) == 2

    conn.rollback()
    loser = conn.execute(
        "SELECT beatport_id, merged_into_id FROM track_identity WHERE id = 1"
    ).fetchone()
    assert loser["beatport_id"] == "BP-1"
    assert loser["merged_into_id"] is None
    conn.close()


def test_merge_group_by_repointing_assets_does_not_manage_outer_transaction_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    trace: list[str] = []
    conn.set_trace_callback(trace.append)
    create_schema_v3(conn)
    _seed_merge_fixture(conn)

    def _boom(_conn: sqlite3.Connection) -> None:
        raise RuntimeError("post-merge failure")

    monkeypatch.setattr("tagslut.storage.v3.merge_identities._assert_asset_link_unique", _boom)

    trace.clear()
    conn.execute("BEGIN")
    with pytest.raises(RuntimeError, match="post-merge failure"):
        merge_group_by_repointing_assets(conn, 2, [1], dry_run=False)

    assert conn.in_transaction is True
    assert not _trace_has_sql(trace, "BEGIN IMMEDIATE")
    assert not _trace_has_exact_statement(trace, "COMMIT")
    assert not _trace_has_exact_statement(trace, "ROLLBACK")

    loser = conn.execute(
        "SELECT beatport_id, merged_into_id FROM track_identity WHERE id = 1"
    ).fetchone()
    assert loser["beatport_id"] is None
    assert int(loser["merged_into_id"]) == 2

    conn.rollback()
    loser = conn.execute(
        "SELECT beatport_id, merged_into_id FROM track_identity WHERE id = 1"
    ).fetchone()
    assert loser["beatport_id"] == "BP-1"
    assert loser["merged_into_id"] is None
    conn.close()


def test_merge_group_by_repointing_assets_rolls_back_without_outer_transaction(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)
    conn.executemany(
        "INSERT INTO asset_file (id, path) VALUES (?, ?)",
        [
            (1, "/music/a1.flac"),
            (2, "/music/a2.flac"),
        ],
    )
    conn.executemany(
        """
            INSERT INTO track_identity (
                id,
                identity_key,
                beatport_id,
                canonical_artist,
                canonical_title,
                enriched_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "beatport:BP-1-a", "BP-1", "Artist A", "Track A", None),
                (2, "beatport:BP-1-b", "BP-2", None, None, "2026-03-04T00:00:00Z"),
            ],
        )
    conn.executemany(
        "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
        [
            (1, 1),
            (2, 2),
        ],
    )
    conn.execute(
        """
        INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version)
        VALUES (1, 1, 1.0, '{}', 1)
        """
    )
    conn.commit()

    def _boom(_conn: sqlite3.Connection) -> None:
        raise RuntimeError("post-merge failure")

    monkeypatch.setattr("tagslut.storage.v3.merge_identities._assert_asset_link_unique", _boom)

    with pytest.raises(RuntimeError, match="post-merge failure"):
        merge_group_by_repointing_assets(conn, 2, [1], dry_run=False)

    loser = conn.execute(
        "SELECT beatport_id, merged_into_id FROM track_identity WHERE id = 1"
    ).fetchone()
    winner = conn.execute(
        "SELECT canonical_artist, canonical_title FROM track_identity WHERE id = 2"
    ).fetchone()
    links = conn.execute(
        "SELECT asset_id, identity_id FROM asset_link ORDER BY asset_id"
    ).fetchall()
    preferred = conn.execute(
        "SELECT identity_id, asset_id FROM preferred_asset ORDER BY identity_id"
    ).fetchall()

    assert loser["beatport_id"] == "BP-1"
    assert loser["merged_into_id"] is None
    assert winner["canonical_artist"] is None
    assert winner["canonical_title"] is None
    assert [tuple(row) for row in links] == [(1, 1), (2, 2)]
    assert [tuple(row) for row in preferred] == [(1, 1)]
    conn.close()
