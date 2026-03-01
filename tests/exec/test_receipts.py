import sqlite3
from pathlib import Path

from tagslut.exec.engine import MoveReceipt, execute_move
from tagslut.exec.receipts import record_move_receipt
from tagslut.storage.schema import init_db, V3_MOVE_EXECUTION_TABLE


def _init_db_file(tmp_path: Path) -> Path:
    db_path = tmp_path / "receipts.db"
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_receipt_creation_and_serialization(tmp_path: Path) -> None:
    src = tmp_path / "a.flac"
    dest = tmp_path / "b" / "a.flac"
    src.write_text("a", encoding="utf-8")

    receipt = execute_move(src, dest, execute=False)
    payload = receipt.to_dict()

    assert payload["status"] == "dry_run"
    assert payload["src"] == str(src)
    assert payload["dest_requested"] == str(dest)
    assert "content_hash" in payload


def test_record_move_receipt_persists_to_db(tmp_path: Path) -> None:
    db_path = _init_db_file(tmp_path)
    src = tmp_path / "src.flac"
    dest = tmp_path / "dest" / "src.flac"
    src.write_text("hello", encoding="utf-8")
    receipt = execute_move(src, dest, execute=True)

    conn = sqlite3.connect(db_path)
    try:
        result = record_move_receipt(
            conn,
            receipt=receipt,
            plan_id=None,
            action="move",
            zone="library",
            mgmt_status="moved",
            script_name="test_receipts",
        )
        conn.commit()
        row = conn.execute(
            f"SELECT id, status FROM {V3_MOVE_EXECUTION_TABLE} WHERE id = ?",
            (result.move_execution_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[1] == "moved"


def test_receipt_dedup_same_file_moved_twice_records_both_events(tmp_path: Path) -> None:
    db_path = _init_db_file(tmp_path)
    src = tmp_path / "x.flac"
    dest = tmp_path / "dst" / "x.flac"
    src.write_text("x", encoding="utf-8")

    first = execute_move(src, dest, execute=True)
    second = MoveReceipt(
        status="skip_missing",
        src=src,
        dest_requested=dest,
        execute=True,
        collision_policy="skip",
        started_at=first.started_at,
        completed_at=first.completed_at,
        error="source_missing",
    )

    conn = sqlite3.connect(db_path)
    try:
        record_move_receipt(
            conn,
            receipt=first,
            plan_id=None,
            action="move",
            zone="library",
            mgmt_status="moved",
            script_name="test_receipts",
        )
        record_move_receipt(
            conn,
            receipt=second,
            plan_id=None,
            action="move",
            zone="library",
            mgmt_status="moved",
            script_name="test_receipts",
        )
        conn.commit()
        count = conn.execute(f"SELECT COUNT(*) FROM {V3_MOVE_EXECUTION_TABLE}").fetchone()[0]
    finally:
        conn.close()

    assert int(count) == 2
