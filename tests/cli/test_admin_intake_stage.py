from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import tagslut.cli.commands.intake as intake_mod
from tagslut.cli.main import cli


def _ok_result(stdout: str) -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def test_admin_intake_stage_calls_steps_in_order(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    db_path = tmp_path / "music.db"
    db_path.write_text("", encoding="utf-8")
    library = tmp_path / "library"
    library.mkdir()

    calls: list[list[str]] = []

    def _fake_run(cmd, capture_output=False, text=False):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if len(calls) == 1:
            return _ok_result(
                "RESULTS\n"
                "  Total:            1\n"
                "  Registered:       1  ✓\n"
                "  Skipped:          0\n"
                "  Errors:           0  \n"
            )
        if len(calls) == 2:
            return _ok_result(
                "DURATION CHECK RESULTS\n"
                "  Total:             1\n"
                "  Updated:           1\n"
                "  Missing DB:        0\n"
                "  Errors:            0  \n"
            )
        return _ok_result("Phases: enrich,art,promote\n")

    monkeypatch.setattr(intake_mod.subprocess, "run", _fake_run)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "admin",
            "intake",
            "stage",
            str(root),
            "--source",
            "tidal",
            "--library",
            str(library),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        [
            sys.executable,
            "-m",
            "tagslut",
            "index",
            "register",
            str(root.resolve()),
            "--source",
            "tidal",
            "--db",
            str(db_path.resolve()),
            "--execute",
        ],
        [
            sys.executable,
            "-m",
            "tagslut",
            "index",
            "duration-check",
            str(root.resolve()),
            "--db",
            str(db_path.resolve()),
            "--execute",
        ],
        [
            sys.executable,
            "-m",
            "tagslut",
            "intake",
            "process-root",
            "--root",
            str(root.resolve()),
            "--phases",
            "enrich,art,promote",
            "--library",
            str(library.resolve()),
            "--providers",
            "beatport,tidal",
            "--db",
            str(db_path.resolve()),
        ],
    ]


def test_admin_intake_stage_dry_run_skips_write_flags(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    db_path = tmp_path / "music.db"
    db_path.write_text("", encoding="utf-8")
    library = tmp_path / "library"
    library.mkdir()

    calls: list[list[str]] = []

    def _fake_run(cmd, capture_output=False, text=False):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return _ok_result("RESULTS\n  Registered:       0\n  Skipped:          1\n  Errors:           0\n")

    monkeypatch.setattr(intake_mod.subprocess, "run", _fake_run)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "admin",
            "intake",
            "stage",
            str(root),
            "--source",
            "bpdl",
            "--library",
            str(library),
            "--db",
            str(db_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "--execute" not in calls[0]
    assert "--execute" not in calls[1]
    assert calls[2][-1] == "--dry-run"


def test_admin_intake_stage_stops_on_step_one_error(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    db_path = tmp_path / "music.db"
    db_path.write_text("", encoding="utf-8")
    library = tmp_path / "library"
    library.mkdir()

    calls: list[list[str]] = []

    def _fake_run(cmd, capture_output=False, text=False):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return SimpleNamespace(returncode=3, stdout="boom\n", stderr="")

    monkeypatch.setattr(intake_mod.subprocess, "run", _fake_run)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "admin",
            "intake",
            "stage",
            str(root),
            "--source",
            "legacy",
            "--library",
            str(library),
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code != 0
    assert len(calls) == 1


def test_admin_intake_stage_library_defaults_to_env(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    db_path = tmp_path / "music.db"
    db_path.write_text("", encoding="utf-8")
    library = tmp_path / "env-library"
    library.mkdir()

    calls: list[list[str]] = []

    def _fake_run(cmd, capture_output=False, text=False):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return _ok_result("RESULTS\n  Registered:       1\n  Skipped:          0\n  Errors:           0\n")

    monkeypatch.setenv("MASTER_LIBRARY", str(library))
    monkeypatch.setattr(intake_mod.subprocess, "run", _fake_run)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "admin",
            "intake",
            "stage",
            str(root),
            "--source",
            "qobuz",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "--library" in calls[2]
    idx = calls[2].index("--library")
    assert calls[2][idx + 1] == str(library.resolve())


def test_admin_intake_stage_missing_library_raises_usage_error(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    db_path = tmp_path / "music.db"
    db_path.write_text("", encoding="utf-8")

    calls: list[list[str]] = []

    def _fake_run(cmd, capture_output=False, text=False):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return _ok_result("RESULTS\n  Registered:       1\n  Skipped:          0\n  Errors:           0\n")

    monkeypatch.delenv("MASTER_LIBRARY", raising=False)
    monkeypatch.setattr(intake_mod.subprocess, "run", _fake_run)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "admin",
            "intake",
            "stage",
            str(root),
            "--source",
            "tidal",
            "--db",
            str(db_path),
        ],
    )

    assert result.exit_code != 0
    assert "Missing --library or $MASTER_LIBRARY" in result.output
    assert calls == []
