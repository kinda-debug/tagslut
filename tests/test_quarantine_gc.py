from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from tagslut.storage.schema import init_db


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_quarantine_gc_dry_run_and_execute(tmp_path) -> None:
    quarantine_root = tmp_path / "quarantine"
    old_dir = quarantine_root / "old"
    new_dir = quarantine_root / "new"
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)

    old_file = old_dir / "old.flac"
    new_file = new_dir / "new.flac"
    old_file.write_bytes(b"old")
    new_file.write_bytes(b"new")

    old_age = time.time() - (45 * 86400)
    os.utime(old_file, (old_age, old_age))

    db_path = tmp_path / "music.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.execute(
        """
        INSERT INTO file_quarantine(
            original_path, quarantine_path, sha256, keeper_path, source_zone, reason, tier, plan_id, quarantined_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "/library/old.flac",
            str(old_file),
            "",
            "/library/keeper.flac",
            "accepted",
            "duplicate",
            "safe",
            "plan-1",
            "2026-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    dry_report = tmp_path / "dry.json"
    proc = _run(
        "tools/review/quarantine_gc.py",
        "--root",
        str(quarantine_root),
        "--days",
        "30",
        "--report",
        str(dry_report),
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    dry_payload = json.loads(dry_report.read_text(encoding="utf-8"))
    assert dry_payload["candidate_count"] == 1
    assert dry_payload["deleted_count"] == 0
    assert old_file.exists()
    assert new_file.exists()

    exec_report = tmp_path / "exec.json"
    proc = _run(
        "tools/review/quarantine_gc.py",
        "--root",
        str(quarantine_root),
        "--days",
        "30",
        "--db",
        str(db_path),
        "--report",
        str(exec_report),
        "--execute",
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    exec_payload = json.loads(exec_report.read_text(encoding="utf-8"))
    assert exec_payload["candidate_count"] == 1
    assert exec_payload["deleted_count"] == 1
    assert exec_payload["db_rows_marked_deleted"] == 1
    assert not old_file.exists()
    assert new_file.exists()

    conn = sqlite3.connect(str(db_path))
    deleted_at = conn.execute(
        "SELECT deleted_at, delete_reason FROM file_quarantine WHERE quarantine_path = ?",
        (str(old_file),),
    ).fetchone()
    conn.close()
    assert deleted_at is not None
    assert deleted_at[0]
    assert deleted_at[1] == "retention_expired"
