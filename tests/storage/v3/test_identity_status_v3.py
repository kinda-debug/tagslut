"""Tests for v3 identity lifecycle status management."""

from __future__ import annotations

import importlib.util as _ilu
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tagslut.storage.v3.identity_status import (
    compute_identity_statuses,
    summary_counts,
    upsert_identity_statuses,
)
from tagslut.storage.v3.schema import create_schema_v3


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "db" / "compute_identity_status_v3.py"

_SPEC = _ilu.spec_from_file_location("compute_identity_status_v3", SCRIPT_PATH)
_SCRIPT_MOD = _ilu.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SCRIPT_MOD)


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _create_fixture_db(tmp_path: Path) -> Path:
    db = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)
        conn.executemany(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                isrc,
                beatport_id,
                canonical_artist,
                canonical_title,
                enriched_at,
                merged_into_id,
                created_at,
                updated_at,
                ingested_at,
                ingestion_method,
                ingestion_source,
                ingestion_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')
            """,
            [
                (
                    1,
                    "id:active",
                    "ISRC-ACTIVE",
                    "BP-ACTIVE",
                    "Artist A",
                    "Track A",
                    "",
                    None,
                    "2024-01-01 00:00:00",
                    "2024-01-01 00:00:00",
                ),
                (
                    2,
                    "id:orphan-old-a",
                    "ISRC-ORPHAN-A",
                    "",
                    "",
                    "",
                    "",
                    None,
                    "2024-01-01 00:00:00",
                    "2024-01-01 00:00:00",
                ),
                (
                    3,
                    "id:merged",
                    "ISRC-MERGED",
                    "",
                    "",
                    "",
                    "",
                    1,
                    "2024-01-01 00:00:00",
                    "2024-01-01 00:00:00",
                ),
                (
                    4,
                    "id:orphan-enriched",
                    "ISRC-ENRICHED",
                    "",
                    "",
                    "",
                    "2026-01-01T00:00:00Z",
                    None,
                    "2024-01-01 00:00:00",
                    "2024-01-01 00:00:00",
                ),
                (
                    5,
                    "unidentified:orphan",
                    "",
                    "",
                    "",
                    "",
                    "",
                    None,
                    "2024-01-01 00:00:00",
                    "2024-01-01 00:00:00",
                ),
                (
                    6,
                    "id:orphan-old-b",
                    "ISRC-ORPHAN-B",
                    "BP-ORPHAN-B",
                    "",
                    "",
                    "",
                    None,
                    "2024-01-01 00:00:00",
                    "2024-01-01 00:00:00",
                ),
                (
                    7,
                    "id:orphan-recent",
                    "ISRC-RECENT",
                    "",
                    "",
                    "",
                    "",
                    None,
                    "2026-03-01 00:00:00",
                    "2026-03-01 00:00:00",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO asset_file (id, path, integrity_state)
            VALUES (?, ?, ?)
            """,
            (101, "/music/active.flac", "ok"),
        )
        conn.execute(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            (101, 1),
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _create_no_timestamp_db(tmp_path: Path) -> Path:
    db = tmp_path / "no_ts_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(
            """
            CREATE TABLE track_identity (
                id INTEGER PRIMARY KEY,
                identity_key TEXT NOT NULL,
                enriched_at TEXT,
                merged_into_id INTEGER,
                ingested_at TEXT NOT NULL,
                ingestion_method TEXT NOT NULL,
                ingestion_source TEXT NOT NULL,
                ingestion_confidence TEXT NOT NULL
            );
            CREATE TABLE asset_link (
                id INTEGER PRIMARY KEY,
                asset_id INTEGER,
                identity_id INTEGER
            );
            CREATE TABLE identity_status (
                identity_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL,
                reason_json TEXT NOT NULL DEFAULT '{}',
                version INTEGER NOT NULL,
                computed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            "INSERT INTO track_identity (id, identity_key, enriched_at, merged_into_id, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, ?, ?, ?, '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')",
            (1, "id:no-ts-orphan", "", None),
        )
        conn.execute(
            "INSERT INTO identity_status (identity_id, status, reason_json, version) VALUES (?, ?, ?, ?)",
            (1, "orphan", "{}", 1),
        )
        conn.commit()
    finally:
        conn.close()
    return db


def test_compute_identity_status_marks_active_identity_with_assets(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        statuses = compute_identity_statuses(conn)
    finally:
        conn.close()

    by_id = {row.identity_id: row for row in statuses}
    assert by_id[1].computed_status == "active"
    assert by_id[1].asset_count == 1


def test_compute_identity_status_marks_orphan_identity_without_assets(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        statuses = compute_identity_statuses(conn)
    finally:
        conn.close()

    by_id = {row.identity_id: row for row in statuses}
    assert by_id[2].computed_status == "orphan"
    assert by_id[2].asset_count == 0


def test_merged_identity_excluded_from_upsert_and_counted_as_merged(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        statuses = compute_identity_statuses(conn)
        counts = upsert_identity_statuses(conn, statuses, version=1)
        summary = summary_counts(conn)
    finally:
        conn.close()

    assert all(status.identity_id != 3 for status in statuses)
    assert counts["inserted"] == 6
    assert int(summary["merged_identities"]) == 1
    assert int(summary["status_rows"]) == 6


def test_plan_mode_connection_is_query_only_and_rejects_writes(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = _SCRIPT_MOD._connect_ro(db)
    try:
        query_only = int(conn.execute("PRAGMA query_only").fetchone()[0])
        assert query_only == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO identity_status (identity_id, status, reason_json, version) "
                "VALUES (999, 'orphan', '{}', 1)"
            )
    finally:
        conn.close()


def test_execute_mode_is_idempotent(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)

    first = _run_script("--db", str(db), "--execute", "--version", "1")
    second = _run_script("--db", str(db), "--execute", "--version", "1")

    assert first.returncode == 0, f"STDOUT:\n{first.stdout}\nSTDERR:\n{first.stderr}"
    assert second.returncode == 0, f"STDOUT:\n{second.stdout}\nSTDERR:\n{second.stderr}"
    assert "rows_inserted: 6" in first.stdout
    assert "rows_unchanged: 6" in second.stdout

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        n_rows = int(conn.execute("SELECT COUNT(*) AS n FROM identity_status").fetchone()["n"])
    finally:
        conn.close()

    assert n_rows == 6


def test_archive_orphans_refuses_without_timestamps_unless_override(tmp_path: Path) -> None:
    db = _create_no_timestamp_db(tmp_path)

    refused = _run_script("--db", str(db), "--archive-orphans")
    assert refused.returncode == 1
    assert "archive refused" in refused.stdout

    allowed = _run_script(
        "--db",
        str(db),
        "--archive-orphans",
        "--archive-orphans-no-timestamp-ok",
    )
    assert allowed.returncode == 0, f"STDOUT:\n{allowed.stdout}\nSTDERR:\n{allowed.stderr}"


def test_archive_orphans_archives_only_eligible_rows(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)

    proc = _run_script(
        "--db",
        str(db),
        "--execute",
        "--version",
        "2",
        "--archive-orphans",
        "--archive-orphans-threshold-days",
        "90",
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "archive_applied: 2" in proc.stdout

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT identity_id, status
            FROM identity_status
            ORDER BY identity_id
            """
        ).fetchall()
    finally:
        conn.close()

    by_id = {int(row["identity_id"]): str(row["status"]) for row in rows}
    assert by_id[1] == "active"
    assert by_id[2] == "archived"
    assert by_id[4] == "orphan"
    assert by_id[5] == "orphan"
    assert by_id[6] == "archived"
    assert by_id[7] == "orphan"
