from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from tagslut.cli.commands._cohort_state import OutputResult, RetagResult
from tagslut.cli.main import cli
from tagslut.exec.intake_orchestrator import IntakeResult, IntakeStageResult
from tagslut.storage.schema import init_db
from tagslut.storage.v3 import create_schema_v3, run_pending_v3


def _prepare_db(path: Path) -> Path:
    conn = sqlite3.connect(str(path))
    try:
        create_schema_v3(conn)
        init_db(conn)
        run_pending_v3(conn)
        conn.commit()
    finally:
        conn.close()
    return path


def test_help_surface_shows_only_new_public_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0, result.output
    assert "get" in result.output
    assert "tag" in result.output
    assert "fix" in result.output
    assert "auth" in result.output
    assert "admin" in result.output
    assert "\n  intake" not in result.output
    assert "\n  index" not in result.output
    assert "\n  ops" not in result.output
    assert "\n  provider" not in result.output
    assert "\n  token-get" not in result.output


def test_get_url_dispatches_to_intake_adapter(tmp_path: Path, monkeypatch) -> None:
    db_path = _prepare_db(tmp_path / "url.db")
    artifact_path = tmp_path / "enrich_paths.txt"
    flac_path = tmp_path / "track.flac"
    flac_path.write_bytes(b"fake")
    artifact_path.write_text(f"{flac_path}\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def _fake_run_intake(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return IntakeResult(
            url=str(kwargs["url"]),
            stages=[
                IntakeStageResult(stage="precheck", status="ok"),
                IntakeStageResult(stage="download", status="ok"),
                IntakeStageResult(stage="promote", status="ok", artifact_path=artifact_path),
                IntakeStageResult(stage="enrich", status="ok", artifact_path=artifact_path),
            ],
            disposition="completed",
            precheck_summary={"total": 1, "new": 1, "upgrade": 0, "blocked": 0},
            precheck_csv=None,
            artifact_path=None,
        )

    monkeypatch.setattr("tagslut.cli.commands.get.run_intake", _fake_run_intake)
    monkeypatch.setattr(
        "tagslut.cli.commands.get.build_output_artifacts",
        lambda **_kwargs: OutputResult(ok=True, stage=None, reason=None, mp3_paths=[], playlist_paths=[]),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["get", "https://example.com/playlist/123", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert captured["url"] == "https://example.com/playlist/123"
    assert captured["tag"] is True
    assert captured["mp3"] is False
    assert captured["dj"] is False


def test_get_local_path_dispatches_to_register_and_retag(tmp_path: Path, monkeypatch) -> None:
    db_path = _prepare_db(tmp_path / "local.db")
    flac_path = tmp_path / "album" / "track.flac"
    flac_path.parent.mkdir(parents=True, exist_ok=True)
    flac_path.write_bytes(b"fake")

    calls: list[list[str]] = []

    monkeypatch.setattr(
        "tagslut.cli.commands.get.run_tagslut_wrapper",
        lambda args: calls.append(list(args)),
    )
    monkeypatch.setattr(
        "tagslut.cli.commands.get.retag_flac_paths",
        lambda **_kwargs: RetagResult(ok_paths=[flac_path.resolve()], blocked={}),
    )
    monkeypatch.setattr(
        "tagslut.cli.commands.get.build_output_artifacts",
        lambda **_kwargs: OutputResult(ok=True, stage=None, reason=None, mp3_paths=[], playlist_paths=[]),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["get", str(flac_path.parent), "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert calls == [
        [
            "index",
            "register",
            str(flac_path.parent.resolve()),
            "--source",
            "local_path",
            "--db",
            str(db_path),
            "--execute",
        ]
    ]


def test_get_fix_rejects_local_path_with_exact_message(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path / "fix.db")
    flac_path = tmp_path / "track.flac"
    flac_path.write_bytes(b"fake")

    runner = CliRunner()
    result = runner.invoke(cli, ["get", str(flac_path), "--db", str(db_path), "--fix"])

    assert result.exit_code != 0
    assert (
        "--fix is not valid on a local path. Use tagslut fix <cohort_id> or tagslut get <url> --fix to resume a remote cohort."
        in result.output
    )
