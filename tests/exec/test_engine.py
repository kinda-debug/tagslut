from pathlib import Path

from tagslut.exec.engine import MovePlanItem, execute_move, execute_move_plan, verify_receipt


def test_move_plan_execution_moves_file(tmp_path: Path) -> None:
    src = tmp_path / "src.flac"
    dest = tmp_path / "dest" / "src.flac"
    src.write_text("audio", encoding="utf-8")

    receipt = execute_move(src, dest, execute=True)

    assert receipt.status == "moved"
    assert not src.exists()
    assert dest.exists()


def test_quarantine_plan_execution_moves_to_quarantine_path(tmp_path: Path) -> None:
    src = tmp_path / "library" / "bad.flac"
    dest = tmp_path / "quarantine" / "bad.flac"
    src.parent.mkdir(parents=True)
    src.write_text("bad", encoding="utf-8")

    receipt = execute_move(src, dest, execute=True)

    assert receipt.status == "moved"
    assert dest.exists()
    assert receipt.dest_final == dest


def test_execute_move_handles_missing_source_file(tmp_path: Path) -> None:
    src = tmp_path / "missing.flac"
    dest = tmp_path / "dest" / "missing.flac"

    receipt = execute_move(src, dest, execute=True)

    assert receipt.status == "skip_missing"
    assert receipt.error == "source_missing"


def test_successful_move_receipt_verification(tmp_path: Path) -> None:
    src = tmp_path / "ok.flac"
    dest = tmp_path / "done" / "ok.flac"
    src.write_text("bytes", encoding="utf-8")

    receipt = execute_move(src, dest, execute=True)
    ok, issues = verify_receipt(receipt)

    assert receipt.status == "moved"
    assert ok is True
    assert issues == []


def test_execute_move_plan_full_flow(tmp_path: Path) -> None:
    src1 = tmp_path / "incoming" / "a.flac"
    src2 = tmp_path / "incoming" / "b.flac"
    dest1 = tmp_path / "library" / "a.flac"
    dest2 = tmp_path / "library" / "b.flac"
    src1.parent.mkdir(parents=True)
    src1.write_text("a", encoding="utf-8")
    src2.write_text("b", encoding="utf-8")

    receipts = execute_move_plan(
        [
            MovePlanItem(src=src1, dest=dest1),
            MovePlanItem(src=src2, dest=dest2),
        ],
        execute=True,
    )

    assert len(receipts) == 2
    assert all(r.status == "moved" for r in receipts)
    assert dest1.exists()
    assert dest2.exists()
    assert not src1.exists()
    assert not src2.exists()
