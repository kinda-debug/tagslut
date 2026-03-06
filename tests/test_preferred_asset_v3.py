"""Tests for deterministic preferred-asset selection in v3."""

from __future__ import annotations

import importlib.util as _ilu
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tagslut.storage.v3.preferred_asset import (
    choose_preferred_asset_for_identity,
    compute_preferred_assets,
)
from tagslut.storage.v3.schema import create_schema_v3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "db" / "compute_preferred_asset_v3.py"

_SPEC = _ilu.spec_from_file_location("compute_preferred_asset_v3", SCRIPT_PATH)
_SCRIPT_MOD = _ilu.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SCRIPT_MOD)


def _create_fixture_db(tmp_path: Path) -> Path:
    db = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)

        conn.executemany(
            """
            INSERT INTO track_identity (id, identity_key, merged_into_id)
            VALUES (?, ?, ?)
            """,
            [
                (1, "id:one", None),
                (2, "id:two", None),
                (3, "id:three", None),
                (4, "id:four-merged", 3),
                (5, "id:five-no-assets", None),
            ],
        )

        conn.executemany(
            """
            INSERT INTO asset_file (
                id, path, integrity_state, flac_ok, bit_depth, sample_rate,
                sha256_checked_at, content_sha256, size_bytes, mtime
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "/music/c_low.flac", "failed", 1, 24, 96000, "2026-03-01T00:00:00Z", "sha1", 5000, 300.0),
                (2, "/music/b_ok.flac", "ok", 0, 16, 44100, None, None, 4000, 100.0),
                (3, "/music/a_ok_better.flac", "ok", 1, 24, 96000, "2026-03-01T00:00:00Z", "sha3", 6000, 200.0),
                (4, "/music/z_tie.flac", None, 1, 24, 48000, "2026-03-01T00:00:00Z", "sha4", 3000, 150.0),
                (5, "/music/a_tie.flac", None, 1, 24, 48000, "2026-03-01T00:00:00Z", "sha5", 3000, 150.0),
                (6, "/music/active_three.flac", "ok", 1, 16, 44100, "2026-03-01T00:00:00Z", "sha6", 2000, 100.0),
                (7, "/music/merged_four.flac", "ok", 1, 24, 96000, "2026-03-01T00:00:00Z", "sha7", 8000, 400.0),
            ],
        )

        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            [
                (1, 1),
                (2, 1),
                (3, 1),
                (4, 2),
                (5, 2),
                (6, 3),
                (7, 4),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_choose_preferred_asset_deterministic_on_quality_and_integrity(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        choice = choose_preferred_asset_for_identity(conn, 1)
    finally:
        conn.close()

    assert choice.asset_id == 3
    assert choice.chosen_path == "/music/a_ok_better.flac"
    assert '"integrity_rank":2' in choice.reason_json


def test_tie_breaker_by_path_is_stable(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        choice = choose_preferred_asset_for_identity(conn, 2)
    finally:
        conn.close()

    assert choice.asset_id == 5
    assert choice.chosen_path == "/music/a_tie.flac"


def test_compute_preferred_assets_excludes_merged_identities(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        choices = list(compute_preferred_assets(conn))
    finally:
        conn.close()

    by_identity = {choice.identity_id: choice for choice in choices}
    assert set(by_identity.keys()) == {1, 2, 3}
    assert 4 not in by_identity
    assert 5 not in by_identity  # active identity with zero assets is skipped


def test_execute_mode_upserts_and_preserves_fk_integrity(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)

    proc = _run_script("--db", str(db), "--execute", "--version", "2")
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "mode: execute" in proc.stdout
    assert "rows_written: 3" in proc.stdout

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        preferred_count = conn.execute(
            "SELECT COUNT(*) AS n FROM preferred_asset"
        ).fetchone()["n"]
        chosen_path_id2 = conn.execute(
            """
            SELECT af.path AS path
            FROM preferred_asset pa
            JOIN asset_file af ON af.id = pa.asset_id
            WHERE pa.identity_id = 2
            """
        ).fetchone()["path"]
        fk_issues = conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()

    assert int(preferred_count) == 3
    assert chosen_path_id2 == "/music/a_tie.flac"
    assert fk_issues == []


def test_plan_mode_connection_uses_query_only_and_rejects_writes(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = _SCRIPT_MOD._connect_ro(db)
    try:
        query_only = int(conn.execute("PRAGMA query_only").fetchone()[0])
        assert query_only == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) "
                "VALUES (1,1,1.0,'{}',1)"
            )
    finally:
        conn.close()
