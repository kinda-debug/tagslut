"""Phase 1 script-level tests for backfill/parity tooling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dedupe.storage.schema import init_db

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _init_db(path: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(str(path))
    init_db(conn)
    conn.close()


def test_validate_v3_dual_write_parity_script(tmp_path) -> None:
    db_path = tmp_path / "phase1.db"
    _init_db(db_path)

    proc = subprocess.run(
        [sys.executable, "scripts/validate_v3_dual_write_parity.py", "--db", str(db_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_backfill_scripts_dry_run(tmp_path) -> None:
    db_path = tmp_path / "phase1.db"
    _init_db(db_path)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "moves.jsonl").write_text(
        (
            '{"event":"move_from_plan","timestamp":"2026-02-09T00:00:00Z",'
            '"src":"/a.flac","dest":"/b.flac","result":"dry_run","execute":false}\n'
        ),
        encoding="utf-8",
    )

    proc_identity = subprocess.run(
        [sys.executable, "scripts/backfill_v3_identity_links.py", "--db", str(db_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_identity.returncode == 0, (
        f"Identity backfill failed.\nSTDOUT:\n{proc_identity.stdout}\n"
        f"STDERR:\n{proc_identity.stderr}"
    )

    proc_prov = subprocess.run(
        [
            sys.executable,
            "scripts/backfill_v3_provenance_from_logs.py",
            "--db",
            str(db_path),
            "--logs",
            str(logs_dir),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_prov.returncode == 0, (
        f"Provenance backfill failed.\nSTDOUT:\n{proc_prov.stdout}\n"
        f"STDERR:\n{proc_prov.stderr}"
    )
