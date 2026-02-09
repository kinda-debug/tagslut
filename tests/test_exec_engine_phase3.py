"""Phase 3 centralized executor unit coverage."""

from __future__ import annotations

from dataclasses import replace

from dedupe.exec.engine import EXECUTOR_CONTRACT_VERSION, execute_move, verify_receipt


def _write(path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def test_execute_move_dry_run_receipt(tmp_path) -> None:
    src = tmp_path / "src.bin"
    dest = tmp_path / "dest.bin"
    _write(src, b"phase3")

    receipt = execute_move(src, dest, execute=False)
    assert receipt.status == "dry_run"
    assert receipt.verification == "size_eq"
    assert receipt.verification_ok
    assert receipt.executor_contract == EXECUTOR_CONTRACT_VERSION
    assert len(receipt.content_hash) == 64
    assert src.exists()
    assert not dest.exists()


def test_execute_move_execute_and_verify(tmp_path) -> None:
    src = tmp_path / "src.bin"
    dest = tmp_path / "dest.bin"
    _write(src, b"payload")

    receipt = execute_move(src, dest, execute=True)
    assert receipt.status == "moved"
    assert receipt.dest_final == dest
    assert not src.exists()
    assert dest.exists()
    ok, errors = verify_receipt(receipt)
    assert ok
    assert errors == []


def test_execute_move_abort_policy_on_existing_destination(tmp_path) -> None:
    src = tmp_path / "src.bin"
    dest = tmp_path / "dest.bin"
    _write(src, b"left")
    _write(dest, b"right")

    receipt = execute_move(src, dest, execute=True, collision_policy="abort")
    assert receipt.status == "skip_dest_exists"
    assert receipt.error == "destination_exists_abort"
    assert src.exists()
    assert dest.read_bytes() == b"right"


def test_execute_move_dedupe_policy_on_existing_destination(tmp_path) -> None:
    src = tmp_path / "src.bin"
    dest = tmp_path / "dest.bin"
    _write(src, b"incoming")
    _write(dest, b"existing")

    receipt = execute_move(src, dest, execute=True, collision_policy="dedupe")
    assert receipt.status == "moved"
    assert receipt.dest_final is not None
    assert receipt.dest_final != dest
    assert "__dup_" in receipt.dest_final.name
    assert receipt.dest_final.read_bytes() == b"incoming"


def test_verify_receipt_detects_tampered_destination(tmp_path) -> None:
    src = tmp_path / "src.bin"
    dest = tmp_path / "dest.bin"
    _write(src, b"payload")
    receipt = execute_move(src, dest, execute=True)
    assert receipt.status == "moved"
    dest.unlink()

    tampered = replace(receipt, dest_final=dest)
    ok, errors = verify_receipt(tampered)
    assert not ok
    assert "dest_missing" in errors
