from pathlib import Path

from tagslut.exec.engine import execute_move, verify_receipt


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
