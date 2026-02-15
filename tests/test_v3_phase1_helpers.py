"""Phase 1 v3 schema and helper tests."""

from __future__ import annotations

import sqlite3

from tagslut.storage.schema import init_db
from tagslut.storage.v3 import (
    dual_write_enabled,
    dual_write_registered_file,
    ensure_move_plan,
    insert_move_execution,
    move_asset_path,
    record_provenance_event,
    upsert_asset_file,
)


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def test_v3_tables_exist_after_init(tmp_path) -> None:
    db_path = tmp_path / "phase1.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    names = _table_names(conn)
    conn.close()

    assert "asset_file" in names
    assert "track_identity" in names
    assert "asset_link" in names
    assert "provenance_event" in names
    assert "move_plan" in names
    assert "move_execution" in names


def test_dual_write_enabled_from_env(monkeypatch) -> None:
    monkeypatch.setenv("TAGSLUT_V3_DUAL_WRITE", "1")
    assert dual_write_enabled() is True
    monkeypatch.setenv("TAGSLUT_V3_DUAL_WRITE", "0")
    assert dual_write_enabled() is False


def test_dual_write_registered_file_creates_asset_identity_and_link(tmp_path) -> None:
    db_path = tmp_path / "phase1.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)

    asset_id, identity_id = dual_write_registered_file(
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
    conn.commit()

    assert asset_id > 0
    assert identity_id is not None

    asset_count = conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0]
    link_count = conn.execute("SELECT COUNT(*) FROM asset_link").fetchone()[0]
    event_count = conn.execute(
        "SELECT COUNT(*) FROM provenance_event WHERE event_type = 'registered'"
    ).fetchone()[0]
    conn.close()

    assert asset_count == 1
    assert link_count == 1
    assert event_count == 1


def test_move_helpers_create_move_execution_and_provenance(tmp_path) -> None:
    db_path = tmp_path / "phase1.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)

    upsert_asset_file(conn, path="/src/a.flac", content_sha256="h1")
    plan_id = ensure_move_plan(
        conn,
        plan_key="test-plan",
        plan_type="move_from_plan",
        plan_path="/tmp/plan.csv",
        policy_version="phase1",
        context={"k": "v"},
    )
    asset_id = move_asset_path(
        conn,
        source_path="/src/a.flac",
        dest_path="/dest/a.flac",
        update_fields={"mgmt_status": "moved_from_plan"},
    )
    move_execution_id = insert_move_execution(
        conn,
        plan_id=plan_id,
        asset_id=asset_id,
        source_path="/src/a.flac",
        dest_path="/dest/a.flac",
        action="MOVE",
        status="moved",
        verification="size_eq",
        error=None,
        details={"reason": "test"},
        executed_at="2026-02-09T00:00:00Z",
    )
    record_provenance_event(
        conn,
        event_type="move_execution",
        status="moved",
        asset_id=asset_id,
        move_plan_id=plan_id,
        move_execution_id=move_execution_id,
        source_path="/src/a.flac",
        dest_path="/dest/a.flac",
        details={"script": "test"},
        event_time="2026-02-09T00:00:00Z",
    )
    conn.commit()

    moved_asset = conn.execute(
        "SELECT path FROM asset_file WHERE id = ?",
        (asset_id,),
    ).fetchone()
    assert moved_asset is not None
    assert moved_asset[0] == "/dest/a.flac"

    exec_count = conn.execute("SELECT COUNT(*) FROM move_execution").fetchone()[0]
    prov_count = conn.execute("SELECT COUNT(*) FROM provenance_event").fetchone()[0]
    conn.close()

    assert exec_count == 1
    assert prov_count == 1
