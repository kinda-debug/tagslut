import json
from pathlib import Path

from tagslut.utils.file_operations import FileOperations
from tagslut.utils.safety_gates import SafetyGates


class DummyUI:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def print(self, message: str) -> None:
        self.messages.append(message)

    def warning(self, message: str) -> None:
        self.messages.append(f"warning:{message}")

    def error(self, message: str, exit_code: int | None = None) -> None:
        self.messages.append(f"error:{message}")
        _ = exit_code

    def confirm(self, prompt: str, required_phrase: str) -> bool:
        _ = prompt
        _ = required_phrase
        return True


def _read_audit_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_safe_move_dry_run_writes_audit(tmp_path: Path) -> None:
    ui = DummyUI()
    gates = SafetyGates(ui)  # type: ignore[arg-type]
    audit = tmp_path / "move_audit.jsonl"
    ops = FileOperations(ui=ui, gates=gates, dry_run=True, audit_log_path=audit)  # type: ignore[arg-type]

    src = tmp_path / "source.flac"
    dest = tmp_path / "dest" / "source.flac"
    ok = ops.safe_move(src, dest)

    assert ok is True
    lines = _read_audit_lines(audit)
    assert lines[-1]["result"] == "dry_run"
    assert lines[-1]["src"] == str(src)
    assert lines[-1]["dest"] == str(dest)


def test_safe_move_refuses_existing_destination(tmp_path: Path) -> None:
    ui = DummyUI()
    gates = SafetyGates(ui)  # type: ignore[arg-type]
    audit = tmp_path / "move_audit.jsonl"
    ops = FileOperations(ui=ui, gates=gates, dry_run=False, audit_log_path=audit)  # type: ignore[arg-type]

    src = tmp_path / "a.flac"
    dest = tmp_path / "out" / "a.flac"
    src.write_text("source", encoding="utf-8")
    dest.parent.mkdir(parents=True)
    dest.write_text("existing", encoding="utf-8")

    ok = ops.safe_move(src, dest, skip_confirmation=True, allow_overwrite=False)

    assert ok is False
    assert src.exists()
    assert dest.read_text(encoding="utf-8") == "existing"
    lines = _read_audit_lines(audit)
    assert lines[-1]["result"] == "skip_dest_exists"


def test_safe_copy_uses_move_semantics(tmp_path: Path) -> None:
    ui = DummyUI()
    gates = SafetyGates(ui)  # type: ignore[arg-type]
    audit = tmp_path / "move_audit.jsonl"
    ops = FileOperations(ui=ui, gates=gates, dry_run=False, audit_log_path=audit)  # type: ignore[arg-type]

    src = tmp_path / "track.flac"
    dest = tmp_path / "usb" / "track.flac"
    src.write_text("audio-bytes", encoding="utf-8")

    ok = ops.safe_copy(src, dest, skip_confirmation=True)

    assert ok is True
    assert not src.exists()
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "audio-bytes"
    lines = _read_audit_lines(audit)
    assert lines[-1]["result"] == "moved"
