import sqlite3
from pathlib import Path

import pytest

from tagslut.storage.models import FileMetadataArchive, ScanIssue, ScanQueueItem, ScanRun
from tagslut.storage.schema import init_db


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _table_columns(conn, table: str) -> set:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_scan_runs_table_exists(mem_db):
    cols = _table_columns(mem_db, "scan_runs")
    assert "library_root" in cols
    assert "mode" in cols
    assert "completed_at" in cols


def test_scan_queue_table_exists(mem_db):
    cols = _table_columns(mem_db, "scan_queue")
    assert "run_id" in cols
    assert "state" in cols
    assert "stage" in cols
    assert "last_error" in cols


def test_scan_issues_table_exists(mem_db):
    cols = _table_columns(mem_db, "scan_issues")
    assert "issue_code" in cols
    assert "severity" in cols
    assert "evidence_json" in cols


def test_file_metadata_archive_table_exists(mem_db):
    cols = _table_columns(mem_db, "file_metadata_archive")
    assert "checksum" in cols
    assert "raw_tags_json" in cols
    assert "isrc_candidates_json" in cols
    assert "identity_confidence" in cols


def test_file_path_history_table_exists(mem_db):
    cols = _table_columns(mem_db, "file_path_history")
    assert "checksum" in cols
    assert "path" in cols
    assert "first_seen_at" in cols


def test_files_table_has_scan_columns(mem_db):
    cols = _table_columns(mem_db, "files")
    for col in [
        "scan_status",
        "scan_flags_json",
        "actual_duration",
        "duration_delta",
        "identity_confidence",
        "isrc_candidates_json",
        "duplicate_of_checksum",
        "last_scanned_at",
        "scan_stage_reached",
    ]:
        assert col in cols, f"Missing column: {col}"


def test_init_db_is_idempotent(mem_db):
    init_db(mem_db)
    init_db(mem_db)


def test_scan_queue_item_path_coercion():
    _ = ScanRun(library_root="/music")
    _ = ScanIssue(run_id=1, path="/music/track.flac", issue_code="X", severity="INFO", evidence_json="{}")
    item = ScanQueueItem(run_id=1, path="/music/track.flac")
    assert isinstance(item.path, Path)


def test_file_metadata_archive_path_coercion():
    archive = FileMetadataArchive(
        checksum="abc123",
        first_seen_at="2026-01-01",
        first_seen_path="/music/track.flac",
        raw_tags_json="{}",
        technical_json="{}",
        durations_json="{}",
        isrc_candidates_json="[]",
        identity_confidence=80,
    )
    assert isinstance(archive.first_seen_path, Path)
