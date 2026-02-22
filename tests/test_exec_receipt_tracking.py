"""Phase 3 receipt persistence + legacy DB mutation contract tests."""

from __future__ import annotations

import sqlite3

import pytest

from tagslut.exec import execute_move, record_move_receipt, update_legacy_path_with_receipt
from tagslut.storage.schema import init_db


def _write(path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_receipt_persistence_and_legacy_path_update(tmp_path) -> None:
    db_path = tmp_path / "phase3.db"
    src = tmp_path / "src" / "track.flac"
    dest = tmp_path / "dest" / "track.flac"
    _write(src, b"phase3-receipt")

    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.execute(
        "INSERT INTO files(path, zone, mgmt_status) VALUES (?, ?, ?)",
        (str(src), "staging", "planned"),
    )
    conn.commit()

    receipt = execute_move(src, dest, execute=True)
    assert receipt.status == "moved"

    write_result = record_move_receipt(
        conn,
        receipt=receipt,
        plan_id=None,
        action="MOVE",
        zone="staging",
        mgmt_status="moved_from_plan",
        script_name="tests/test_exec_receipts_phase3.py",
        details={"test": "phase3"},
    )
    update_legacy_path_with_receipt(
        conn,
        move_execution_id=write_result.move_execution_id,
        receipt=receipt,
        zone="staging",
        mgmt_status="moved_from_plan",
    )
    conn.commit()

    moved_status = conn.execute(
        "SELECT status FROM move_execution WHERE id = ?",
        (write_result.move_execution_id,),
    ).fetchone()[0]
    legacy_row = conn.execute(
        "SELECT path, original_path FROM files WHERE path = ?",
        (str(dest),),
    ).fetchone()
    conn.close()

    assert moved_status == "moved"
    assert legacy_row is not None
    assert legacy_row[0] == str(dest)
    assert legacy_row[1] == str(src)


def test_legacy_path_update_requires_moved_receipt(tmp_path) -> None:
    db_path = tmp_path / "phase3.db"
    src = tmp_path / "src" / "track.flac"
    dest = tmp_path / "dest" / "track.flac"
    _write(src, b"dry-run")

    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.execute(
        "INSERT INTO files(path, zone, mgmt_status) VALUES (?, ?, ?)",
        (str(src), "staging", "planned"),
    )
    conn.commit()

    receipt = execute_move(src, dest, execute=False)
    assert receipt.status == "dry_run"
    write_result = record_move_receipt(
        conn,
        receipt=receipt,
        plan_id=None,
        action="MOVE",
        zone="staging",
        mgmt_status="planned",
        script_name="tests/test_exec_receipts_phase3.py",
    )

    with pytest.raises(ValueError, match="moved receipt"):
        update_legacy_path_with_receipt(
            conn,
            move_execution_id=write_result.move_execution_id,
            receipt=receipt,
            zone="staging",
            mgmt_status="moved_from_plan",
        )
    conn.close()
