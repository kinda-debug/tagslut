from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import tagslut.cli.commands.intake as intake_mod
from tagslut.cli.main import cli


def _ok_result(stdout: str) -> SimpleNamespace:
    return SimpleNamespace(returncode=0, stdout=stdout, stderr="")


def test_admin_intake_stage_refreshes_integrity_before_process_root(monkeypatch, tmp_path: Path) -> None:
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
                "  Registered:       1\n"
                "  Skipped:          0\n"
                "  Errors:           0\n"
            )
        if len(calls) == 2:
            return _ok_result(
                "DURATION CHECK RESULTS\n"
                "  Updated:           1\n"
                "  Missing DB:        0\n"
                "  Errors:            0\n"
            )
        if len(calls) == 3:
            return _ok_result(
                "EXECUTE: checked=1 valid=1 recoverable=0 corrupt=0\n"
                f"DB: {db_path.resolve()}\n"
            )
        if len(calls) == 4:
            return _ok_result("Scanned: 0 inserted: 0 already in DB: 0 failed: 0\n")
        if len(calls) == 5:
            return _ok_result(
                "RESULTS\n"
                "  Total:            1\n"
                "  Enriched:         1  ✓\n"
                "  No match:         0\n"
                "  Failed:           0\n"
            )
        return _ok_result("move_log=/tmp/fake.jsonl\n")

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
            str((Path(intake_mod.__file__).resolve().parents[3] / "tools/review/check_integrity_update_db.py").resolve()),
            "--db",
            str(db_path.resolve()),
            "--execute",
            str(root.resolve()),
        ],
        [
            sys.executable,
            "-m",
            "tagslut",
            "index",
            "register-mp3",
            "--root",
            str(root.resolve()),
            "--db",
            str(db_path.resolve()),
            "--source",
            "tidal",
            "--execute",
        ],
        [
            sys.executable,
            "-m",
            "tagslut",
            "index",
            "enrich",
            "--db",
            str(db_path.resolve()),
            "--hoarding",
            "--providers",
            "beatport,tidal,qobuz",
            "--path",
            f"{root.resolve()}/%.flac",
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
            "art,promote",
            "--library",
            str(library.resolve()),
            "--providers",
            "beatport,tidal,qobuz",
            "--db",
            str(db_path.resolve()),
            "--verbose",
        ],
    ]
    assert "integrity-check: checked=1 valid=1 recoverable=0 corrupt=0" in result.output
    assert f"{root.resolve()}/%.flac" in result.output
    assert "enrich: total=1 enriched=1 no_match=0 failed=0" in result.output


def test_admin_intake_stage_dry_run_skips_integrity_refresh(monkeypatch, tmp_path: Path) -> None:
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
    assert not any("check_integrity_update_db.py" in arg for call in calls for arg in call)
