from __future__ import annotations

import sqlite3
from pathlib import Path

from tagslut.storage.v3 import create_schema_v3, resolve_latest_dj_export_path


def _setup_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)
    conn.execute("INSERT INTO track_identity (id, identity_key, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (1, 'identity:1', '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')")
    conn.commit()
    return conn


def test_resolve_latest_dj_export_path_returns_latest_success_for_source() -> None:
    conn = _setup_conn()
    try:
        conn.execute(
            """
            INSERT INTO provenance_event (event_type, status, identity_id, source_path, dest_path, event_time)
            VALUES ('dj_export', 'success', 1, '/music/a.flac', '/exports/old.mp3', '2026-03-09 10:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO provenance_event (event_type, status, identity_id, source_path, dest_path, event_time)
            VALUES ('dj_export', 'success', 1, '/music/a.flac', '/exports/new.mp3', '2026-03-09 11:00:00')
            """
        )

        result = resolve_latest_dj_export_path(conn, source_path="/music/a.flac")

        assert result == Path("/exports/new.mp3")
    finally:
        conn.close()


def test_resolve_latest_dj_export_path_ignores_non_success_status() -> None:
    conn = _setup_conn()
    try:
        conn.execute(
            """
            INSERT INTO provenance_event (event_type, status, identity_id, source_path, dest_path, event_time)
            VALUES ('dj_export', 'success', 1, '/music/a.flac', '/exports/good.mp3', '2026-03-09 10:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO provenance_event (event_type, status, identity_id, source_path, dest_path, event_time)
            VALUES ('dj_export', 'failed', 1, '/music/a.flac', '/exports/bad.mp3', '2026-03-09 11:00:00')
            """
        )

        result = resolve_latest_dj_export_path(conn, source_path="/music/a.flac")

        assert result == Path("/exports/good.mp3")
    finally:
        conn.close()


def test_resolve_latest_dj_export_path_both_args_intersection() -> None:
    conn = _setup_conn()
    try:
        conn.execute(
            """
            INSERT INTO provenance_event (event_type, status, identity_id, source_path, dest_path, event_time)
            VALUES ('dj_export', 'success', 1, '/a/track.flac', '/exports/a.mp3', '2026-03-09 10:00:00')
            """
        )

        result = resolve_latest_dj_export_path(
            conn,
            source_path="/b/other.flac",
            identity_id=1,
        )

        assert result is None
    finally:
        conn.close()


def test_resolve_latest_dj_export_path_normalizes_relative_query(monkeypatch, tmp_path: Path) -> None:
    conn = _setup_conn()
    try:
        track_path = tmp_path / "music" / "track.flac"
        track_path.parent.mkdir(parents=True, exist_ok=True)
        track_path.write_bytes(b"fake")
        export_path = tmp_path / "exports" / "track.mp3"
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_bytes(b"mp3")
        conn.execute(
            """
            INSERT INTO provenance_event (event_type, status, identity_id, source_path, dest_path, event_time)
            VALUES ('dj_export', 'success', 1, ?, ?, '2026-03-09 10:00:00')
            """,
            (str(track_path.resolve()), str(export_path.resolve())),
        )
        monkeypatch.chdir(tmp_path)

        result = resolve_latest_dj_export_path(conn, source_path=Path("music/track.flac"))

        assert result == export_path.resolve()
    finally:
        conn.close()
