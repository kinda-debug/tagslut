"""Tests for the temporary move executor compatibility adapter."""

from __future__ import annotations

from dedupe.exec.compat import ADAPTER_CONTRACT_VERSION, execute_move_action


def _write(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_execute_move_action_dry_run_keeps_source(tmp_path) -> None:
    src = tmp_path / "src.bin"
    dest = tmp_path / "dest.bin"
    _write(src, b"abc123")

    outcome = execute_move_action(src, dest, execute=False)
    assert outcome.result == "dry_run"
    assert outcome.dest_final == dest
    assert src.exists()
    assert not dest.exists()
    assert outcome.to_event_fields()["executor_contract"] == ADAPTER_CONTRACT_VERSION


def test_execute_move_action_execute_moves_file(tmp_path) -> None:
    src = tmp_path / "src.bin"
    dest = tmp_path / "dest.bin"
    _write(src, b"payload")

    outcome = execute_move_action(src, dest, execute=True)
    assert outcome.result == "moved"
    assert outcome.dest_final == dest
    assert not src.exists()
    assert dest.exists()
    assert dest.read_bytes() == b"payload"


def test_execute_move_action_skip_missing_source(tmp_path) -> None:
    src = tmp_path / "missing-src.bin"
    dest = tmp_path / "missing-dest.bin"

    outcome = execute_move_action(src, dest, execute=True)
    assert outcome.result == "skip_missing"


def test_execute_move_action_skip_existing_destination(tmp_path) -> None:
    src = tmp_path / "src.bin"
    dest = tmp_path / "dest.bin"
    _write(src, b"left")
    _write(dest, b"right")
    outcome = execute_move_action(src, dest, execute=True, collision_policy="skip")
    assert outcome.result == "skip_dest_exists"
    assert src.exists()
    assert dest.read_bytes() == b"right"


def test_execute_move_action_dedupe_existing_destination(tmp_path) -> None:
    src = tmp_path / "src.bin"
    dest = tmp_path / "dest.bin"
    _write(src, b"incoming")
    _write(dest, b"existing")
    outcome = execute_move_action(src, dest, execute=True, collision_policy="dedupe")
    assert outcome.result == "moved"
    assert outcome.dest_final is not None
    assert outcome.dest_final != dest
    assert "__dup_" in outcome.dest_final.name
    assert outcome.dest_final.read_bytes() == b"incoming"
    assert dest.read_bytes() == b"existing"
