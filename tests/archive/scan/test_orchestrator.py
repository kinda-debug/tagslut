# flake8: noqa: E402

import pytest
pytest.skip("scan module archived", allow_module_level=True)

import json
import sqlite3
from pathlib import Path

import pytest

from tagslut.scan.orchestrator import run_scan, scan_file
from tagslut.storage.schema import init_db


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_scan_file_happy_path_with_injected_dependencies(mem_db):
    issues = []

    def read_tags(_path: Path):
        return ({"TITLE": ["Track"]}, {"duration_tagged": 100.0}, ["USABC1234567"], 4, 100.0)

    def compute_checksum(_path: Path) -> str:
        return "abc123"

    def probe_duration(_path: Path):
        return 100.0

    def decode_probe(_path: Path, _duration):
        return []

    def record_issue_fn(_conn, _run_id, _path, code, _severity, _evidence, _checksum=None):
        issues.append(code)

    result = scan_file(
        mem_db,
        1,
        Path("/music/track.flac"),
        read_tags=read_tags,
        compute_checksum=compute_checksum,
        probe_duration=probe_duration,
        decode_probe=decode_probe,
        record_issue_fn=record_issue_fn,
    )

    assert result["status"] == "CLEAN"
    assert issues == []
    row = mem_db.execute("SELECT scan_status, checksum FROM files WHERE path = ?",
                         ("/music/track.flac",)).fetchone()
    assert row["scan_status"] == "CLEAN"
    assert row["checksum"] == "abc123"


def test_scan_file_records_issue_and_corrupt_on_decode_error(mem_db):
    recorded = []

    def read_tags(_path: Path):
        return ({"TITLE": ["Track"]}, {"duration_tagged": 100.0}, ["USABC1234567"], 4, 100.0)

    def record_issue_fn(_conn, _run_id, _path, code, _severity, _evidence, _checksum=None):
        recorded.append(code)

    result = scan_file(
        mem_db,
        2,
        Path("/music/bad.flac"),
        read_tags=read_tags,
        compute_checksum=lambda _p: "bad123",
        probe_duration=lambda _p: 100.0,
        decode_probe=lambda _p, _d: ["Invalid data found"],
        record_issue_fn=record_issue_fn,
    )

    assert result["status"] == "CORRUPT"
    assert "CORRUPT_DECODE" in recorded


def test_scan_file_writes_issues_and_file_row_in_one_transaction(mem_db):
    def read_tags(_path: Path):
        return ({}, {"duration_tagged": None}, [], None, None)

    scan_file(
        mem_db,
        3,
        Path("/music/no_meta.flac"),
        read_tags=read_tags,
        compute_checksum=lambda _p: "nometa",
        probe_duration=lambda _p: None,
        decode_probe=lambda _p, _d: [],
    )

    issues = mem_db.execute("SELECT issue_code FROM scan_issues WHERE path = ?",
                            ("/music/no_meta.flac",)).fetchall()
    codes = {row["issue_code"] for row in issues}
    assert "DURATION_UNVERIFIED" in codes
    assert "ISRC_MISSING" in codes

    row = mem_db.execute("SELECT path, scan_status FROM files WHERE path = ?",
                         ("/music/no_meta.flac",)).fetchone()
    assert row is not None
    assert row["scan_status"] == "CLEAN"


def test_run_scan_completes_and_sets_run_status(mem_db):
    def discover(_root: Path):
        return [Path("/lib/a.flac"), Path("/lib/b.flac")]

    def scan_file_fn(conn, run_id, path):
        conn.execute("INSERT OR IGNORE INTO files (path, metadata_json) VALUES (?, '{}')", (str(path),))
        return {"status": "CLEAN", "run_id": run_id}

    run_id = run_scan(mem_db, Path("/lib"), discover=discover, scan_file_fn=scan_file_fn)
    row = mem_db.execute(
        "SELECT tool_versions_json, completed_at FROM scan_runs WHERE id = ?", (run_id,)).fetchone()
    status = json.loads(row["tool_versions_json"]).get("status")
    assert status == "COMPLETE"
    assert row["completed_at"] is not None


def test_run_scan_catches_unexpected_and_marks_failed_and_continues(mem_db):
    def discover(_root: Path):
        return [Path("/lib/a.flac"), Path("/lib/b.flac")]

    def scan_file_fn(conn, _run_id, path):
        if path.name == "a.flac":
            raise RuntimeError("boom")
        conn.execute("INSERT OR IGNORE INTO files (path, metadata_json) VALUES (?, '{}')", (str(path),))
        return {"status": "CLEAN"}

    run_id = run_scan(mem_db, Path("/lib"), discover=discover, scan_file_fn=scan_file_fn)

    failed = mem_db.execute(
        "SELECT COUNT(*) AS n FROM scan_queue WHERE run_id = ? AND state = 'FAILED'", (run_id,)).fetchone()["n"]
    done = mem_db.execute(
        "SELECT COUNT(*) AS n FROM scan_queue WHERE run_id = ? AND state = 'DONE'", (run_id,)).fetchone()["n"]
    assert failed == 1
    assert done == 1

    issue = mem_db.execute(
        "SELECT issue_code FROM scan_issues WHERE run_id = ? ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()
    assert issue["issue_code"] == "SCAN_ERROR"

    run_row = mem_db.execute(
        "SELECT tool_versions_json FROM scan_runs WHERE id = ?", (run_id,)).fetchone()
    status = json.loads(run_row["tool_versions_json"]).get("status")
    assert status == "FAILED"


def test_run_scan_testable_without_filesystem(mem_db):
    def discover(_root: Path):
        return [Path("/virtual/one.flac")]

    calls = []

    def scan_file_fn(_conn, _run_id, path):
        calls.append(path)
        return {"status": "CLEAN"}

    run_scan(mem_db, Path("/virtual"), discover=discover, scan_file_fn=scan_file_fn)
    assert calls == [Path("/virtual/one.flac")]
