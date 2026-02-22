"""Ensure plan executor writes receipts even without dual-write flag."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from tagslut.storage.schema import init_db

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_move_from_plan_records_receipt_and_updates_legacy_path(tmp_path) -> None:
    db_path = tmp_path / "phase3.db"
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    src_root.mkdir(parents=True, exist_ok=True)
    dest_root.mkdir(parents=True, exist_ok=True)

    src_file = src_root / "track.flac"
    src_file.write_bytes(b"phase3-executor")

    plan_csv = tmp_path / "plan.csv"
    plan_csv.write_text(
        "action,path\nMOVE," + str(src_file) + "\n",
        encoding="utf-8",
    )

    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.execute(
        "INSERT INTO files(path, zone, mgmt_status) VALUES (?, ?, ?)",
        (str(src_file), "staging", "planned"),
    )
    conn.commit()
    conn.close()

    proc = subprocess.run(
        [
            sys.executable,
            "tools/review/move_from_plan.py",
            str(plan_csv),
            "--source-root",
            str(src_root),
            "--dest-root",
            str(dest_root),
            "--db",
            str(db_path),
            "--execute",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    moved_file = dest_root / "track.flac"
    assert moved_file.exists()
    assert not src_file.exists()

    conn = sqlite3.connect(str(db_path))
    moved_exec = conn.execute(
        "SELECT COUNT(*) FROM move_execution WHERE status = 'moved'"
    ).fetchone()[0]
    legacy_path = conn.execute(
        "SELECT path FROM files WHERE path = ?",
        (str(moved_file),),
    ).fetchone()
    conn.close()

    assert moved_exec >= 1
    assert legacy_path is not None
