"""Tests for move audit logging in FileOperations."""

from __future__ import annotations

import json

from tagslut.utils.console_ui import ConsoleUI
from tagslut.utils.file_operations import FileOperations
from tagslut.utils.safety_gates import SafetyGates


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_safe_move_dry_run_writes_audit_event(tmp_path) -> None:
    src = tmp_path / "src.flac"
    dest = tmp_path / "dest" / "src.flac"
    log_path = tmp_path / "logs" / "moves.jsonl"
    src.write_bytes(b"abc123")

    ui = ConsoleUI(quiet=True)
    gates = SafetyGates(ui)
    ops = FileOperations(
        ui=ui,
        gates=gates,
        dry_run=True,
        quiet=True,
        audit_log_path=log_path,
    )

    assert ops.safe_move(src, dest, skip_confirmation=True)
    assert src.exists()
    assert not dest.exists()

    events = _read_jsonl(log_path)
    assert len(events) == 1
    assert events[0]["event"] == "file_move"
    assert events[0]["result"] == "dry_run"
    assert events[0]["verification"] == "size_eq+checksum_eq"


def test_safe_move_execute_writes_moved_audit_event(tmp_path) -> None:
    src = tmp_path / "track.flac"
    dest = tmp_path / "library" / "track.flac"
    log_path = tmp_path / "logs" / "moves.jsonl"
    payload = b"move-me"
    src.write_bytes(payload)

    ui = ConsoleUI(quiet=True)
    gates = SafetyGates(ui)
    ops = FileOperations(
        ui=ui,
        gates=gates,
        dry_run=False,
        quiet=True,
        audit_log_path=log_path,
    )

    assert ops.safe_move(src, dest, skip_confirmation=True)
    assert not src.exists()
    assert dest.exists()
    assert dest.read_bytes() == payload

    events = _read_jsonl(log_path)
    assert len(events) == 1
    assert events[0]["event"] == "file_move"
    assert events[0]["result"] == "moved"
    assert events[0]["verification"] == "size_eq+checksum_eq"
    assert events[0]["source_size"] == len(payload)
    assert events[0]["dest_size"] == len(payload)
