"""Tests for scripts/db/check_promotion_preferred_invariant_v3.py."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from tagslut.db.v3.schema import create_schema_v3


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _create_fixture_db(tmp_path: Path) -> Path:
    db = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)
        conn.executemany(
            "INSERT INTO track_identity (id, identity_key) VALUES (?, ?)",
            [
                (1, "id:one"),
                (2, "id:two"),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_file (id, path) VALUES (?, ?)",
            [
                (11, "/ROOT/A/a.flac"),
                (12, "/ROOT/A/b.flac"),
                (21, "/ROOT/B/c.flac"),
                (22, "/ROOT/B/d.flac"),
            ],
        )
        conn.executemany(
            "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) VALUES (?, ?, ?, ?, ?)",
            [
                (1, 11, 1.0, "{}", 1),
                (2, 21, 1.0, "{}", 1),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _run_check(
    *,
    db: Path,
    root: str,
    since: str | None = None,
    minutes: int | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "scripts/db/check_promotion_preferred_invariant_v3.py",
        "--db",
        str(db),
        "--root",
        root,
    ]
    if since is not None:
        cmd.extend(["--since", since])
    if minutes is not None:
        cmd.extend(["--minutes", str(minutes)])
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_pass_case_preferred_under_root_selected(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            """
            INSERT INTO provenance_event (
                event_type, event_time, asset_id, identity_id, source_path, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("promotion_select", "2026-03-04 10:00:00", 11, 1, "/ROOT/A/a.flac", "moved"),
        )
        conn.commit()
    finally:
        conn.close()

    proc = _run_check(db=db, root="/ROOT/A", since="2026-03-04 00:00:00")
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "violation_count: 0" in proc.stdout
    assert "OK: promotion preferred-asset invariant holds" in proc.stdout


def test_fail_case_non_preferred_selected_when_preferred_under_root_exists(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            """
            INSERT INTO provenance_event (
                event_type, event_time, asset_id, identity_id, source_path, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("promotion_select", "2026-03-04 10:00:00", 12, 1, "/ROOT/A/b.flac", "moved"),
        )
        conn.commit()
    finally:
        conn.close()

    proc = _run_check(db=db, root="/ROOT/A", since="2026-03-04 00:00:00")
    assert proc.returncode == 1, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "violation_count: 1" in proc.stdout
    assert "identity_id=1" in proc.stdout
    assert "chosen_asset_id=12" in proc.stdout
    assert "preferred_asset_id=11" in proc.stdout


def test_scope_case_source_path_outside_root_is_ignored(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            """
            INSERT INTO provenance_event (
                event_type, event_time, asset_id, identity_id, source_path, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("promotion_select", "2026-03-04 10:00:00", 22, 2, "/ROOT/B/d.flac", "moved"),
        )
        conn.commit()
    finally:
        conn.close()

    proc = _run_check(db=db, root="/ROOT/A", since="2026-03-04 00:00:00")
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "promoted_rows: 0" in proc.stdout
    assert "violation_count: 0" in proc.stdout


def test_time_window_case_old_event_is_ignored(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            """
            INSERT INTO provenance_event (
                event_type, event_time, asset_id, identity_id, source_path, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("promotion_select", "2020-01-01 00:00:00", 12, 1, "/ROOT/A/b.flac", "moved"),
        )
        conn.commit()
    finally:
        conn.close()

    proc = _run_check(db=db, root="/ROOT/A", since="2026-03-04 00:00:00")
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "promoted_rows: 0" in proc.stdout
    assert "violation_count: 0" in proc.stdout
