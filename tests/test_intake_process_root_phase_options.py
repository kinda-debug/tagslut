"""Tests for intake process-root phase option passthrough."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

from tagslut.cli.main import cli
import tagslut.cli.commands.intake as intake_mod


def test_intake_process_root_passes_scan_only_flag(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    db_path.write_text("", encoding="utf-8")
    calls: list[tuple[str, tuple[str, ...]]] = []

    monkeypatch.setattr(
        intake_mod,
        "resolve_cli_env_db_path",
        lambda *_args, **_kwargs: SimpleNamespace(path=db_path),
    )
    monkeypatch.setattr(
        intake_mod,
        "run_python_script",
        lambda script, args: calls.append((script, tuple(args))),
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "intake",
            "process-root",
            "--db",
            str(db_path),
            "--root",
            str(tmp_path),
            "--scan-only",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls
    script, args = calls[0]
    assert script == "tools/review/process_root.py"
    assert "--scan-only" in args


def test_intake_process_root_passes_phases_option(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    db_path.write_text("", encoding="utf-8")
    calls: list[tuple[str, tuple[str, ...]]] = []

    monkeypatch.setattr(
        intake_mod,
        "resolve_cli_env_db_path",
        lambda *_args, **_kwargs: SimpleNamespace(path=db_path),
    )
    monkeypatch.setattr(
        intake_mod,
        "run_python_script",
        lambda script, args: calls.append((script, tuple(args))),
    )

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "intake",
            "process-root",
            "--db",
            str(db_path),
            "--root",
            str(tmp_path),
            "--phases",
            "register,integrity",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls
    script, args = calls[0]
    assert script == "tools/review/process_root.py"
    assert "--phases" in args
    idx = args.index("--phases")
    assert args[idx + 1] == "register,integrity"
