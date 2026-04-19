from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from tagslut.cli.commands import get as get_command_module
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
    assert captured["verbose"] is True
    assert "Stages:" in result.output
    assert "OK      precheck" in result.output


def test_get_url_with_mp3_dispatches_mp3_stage_and_playlist(tmp_path: Path, monkeypatch) -> None:
    db_path = _prepare_db(tmp_path / "url-mp3.db")
    artifact_path = tmp_path / "enrich_paths.txt"
    mp3_stage_artifact = tmp_path / "mp3_paths.json"
    flac_path = tmp_path / "track.flac"
    flac_path.write_bytes(b"fake")
    artifact_path.write_text(f"{flac_path}\n", encoding="utf-8")
    mp3_stage_artifact.write_text(f'{{"paths": ["{flac_path}"]}}', encoding="utf-8")

    captured: dict[str, object] = {}
    playlist_calls: list[dict[str, object]] = []

    def _fake_run_intake(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return IntakeResult(
            url=str(kwargs["url"]),
            stages=[
                IntakeStageResult(stage="precheck", status="ok"),
                IntakeStageResult(stage="download", status="ok"),
                IntakeStageResult(stage="promote", status="ok", artifact_path=artifact_path),
                IntakeStageResult(stage="enrich", status="ok", artifact_path=artifact_path),
                IntakeStageResult(stage="mp3", status="ok", artifact_path=mp3_stage_artifact),
            ],
            disposition="completed",
            precheck_summary={"total": 1, "new": 1, "upgrade": 0, "blocked": 0},
            precheck_csv=None,
            artifact_path=None,
        )

    monkeypatch.setattr("tagslut.cli.commands.get.run_intake", _fake_run_intake)
    monkeypatch.setattr(
        "tagslut.cli.commands.get._write_url_mp3_playlists",
        lambda **kwargs: playlist_calls.append(dict(kwargs)) or [],
    )
    monkeypatch.setenv("MP3_LIBRARY", str(tmp_path / "MP3_LIBRARY"))

    runner = CliRunner()
    result = runner.invoke(cli, ["get", "https://example.com/album/123", "--db", str(db_path), "--mp3"])

    assert result.exit_code == 0, result.output
    assert captured["url"] == "https://example.com/album/123"
    assert captured["tag"] is True
    assert captured["mp3"] is True
    assert captured["dj"] is False
    assert captured["mp3_root"] == (tmp_path / "MP3_LIBRARY").resolve()
    assert captured["verbose"] is True
    assert len(playlist_calls) == 1
    assert playlist_calls[0]["dj"] is False
    assert "Stages:" in result.output
    assert "OK      mp3" in result.output


def test_write_url_mp3_playlists_writes_named_batch_playlist(tmp_path: Path, monkeypatch) -> None:
    flac_path = tmp_path / "master.flac"
    flac_path.write_bytes(b"fake")
    mp3_root = tmp_path / "MP3_LIBRARY"
    album_dir = mp3_root / "Artist" / "Album Title"
    album_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = album_dir / "track.mp3"
    mp3_path.write_bytes(b"fake-mp3")

    stage_artifact = tmp_path / "mp3_stage.json"
    stage_artifact.write_text(f'{{"paths": ["{flac_path}"]}}', encoding="utf-8")
    named_playlist = tmp_path / "playlists"
    named_playlist.mkdir(parents=True, exist_ok=True)
    source_playlist = named_playlist / "Album Title.m3u"
    source_playlist.write_text("#EXTM3U\n", encoding="utf-8")

    result = IntakeResult(
        url="https://example.com/album/123",
        stages=[IntakeStageResult(stage="mp3", status="ok", artifact_path=stage_artifact)],
        disposition="completed",
        precheck_summary={},
        precheck_csv=None,
        artifact_path=None,
    )

    monkeypatch.setattr(
        "tagslut.cli.commands.get._candidate_m3u_dirs",
        lambda: [named_playlist],
    )
    monkeypatch.setattr(
        "tagslut.exec.mp3_build._mp3_asset_dest_for_flac_path",
        lambda **_kwargs: mp3_path,
    )

    written = get_command_module._write_url_mp3_playlists(
        result=result,
        mp3_root=mp3_root,
        dj=False,
        run_started=source_playlist.stat().st_mtime,
    )

    batch_playlist = album_dir / "Album Title.m3u"
    assert written == [batch_playlist.resolve()]
    assert batch_playlist.exists()
    assert str(mp3_path.resolve()) in batch_playlist.read_text(encoding="utf-8")


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


def test_get_local_path_with_tag_dispatches_to_stage_intake(tmp_path: Path, monkeypatch) -> None:
    db_path = _prepare_db(tmp_path / "stage.db")
    flac_path = tmp_path / "loose" / "track.flac"
    flac_path.parent.mkdir(parents=True, exist_ok=True)
    flac_path.write_bytes(b"fake")

    calls: list[list[str]] = []

    monkeypatch.setattr(
        "tagslut.cli.commands.get.run_tagslut_wrapper",
        lambda args: calls.append(list(args)),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["get", str(flac_path.parent), "--tag", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert calls == [
        [
            "admin",
            "intake",
            "stage",
            str(flac_path.parent.resolve()),
            "--source",
            "legacy",
            "--db",
            str(db_path),
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


def test_get_mp3_rejects_local_path(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path / "mp3-local.db")
    flac_path = tmp_path / "track.flac"
    flac_path.write_bytes(b"fake")

    runner = CliRunner()
    result = runner.invoke(cli, ["get", str(flac_path), "--db", str(db_path), "--mp3"])

    assert result.exit_code != 0
    assert "--mp3 is only supported for URL intake." in result.output
