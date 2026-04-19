from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from tagslut.cli.main import cli
from tagslut.storage.schema import init_db
from tagslut.storage.v3 import create_schema_v3, run_pending_v3


def _seed_blocked_cohort(db_path: Path, *, source_url: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        create_schema_v3(conn)
        init_db(conn)
        run_pending_v3(conn)
        conn.execute(
            """
            INSERT INTO asset_file (id, path, status, blocked_reason)
            VALUES (1, ?, 'blocked', 'enrich:no provider match')
            """,
            ("/tmp/example.flac",),
        )
        conn.execute(
            """
            INSERT INTO cohort (id, source_url, source_kind, status, blocked_reason, created_at, flags)
            VALUES (1, ?, 'url', 'blocked', 'enrich:no provider match', '2026-04-05T00:00:00+00:00', ?)
            """,
            (source_url, '{"command":"get","dj":false,"playlist":false}'),
        )
        conn.execute(
            """
            INSERT INTO cohort_file (
                id, cohort_id, asset_file_id, source_path, status, blocked_reason, blocked_stage, created_at
            ) VALUES (1, 1, 1, ?, 'blocked', 'no provider match', 'enrich', '2026-04-05T00:00:00+00:00')
            """,
            ("/tmp/example.flac",),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_blocked_cohort_at_stage(
    db_path: Path,
    *,
    source_url: str,
    blocked_stage: str,
    flags: str = '{"command":"get","dj":false,"playlist":false}',
) -> None:
    """Seed a single-file cohort blocked at a specific stage."""
    conn = sqlite3.connect(str(db_path))
    try:
        create_schema_v3(conn)
        init_db(conn)
        run_pending_v3(conn)
        conn.execute(
            """
            INSERT INTO asset_file (id, path, status, blocked_reason)
            VALUES (1, '/tmp/example.flac', 'blocked', ?)
            """,
            (f"{blocked_stage}:failed",),
        )
        conn.execute(
            """
            INSERT INTO cohort (
                id, source_url, source_kind, status, blocked_reason, created_at, flags
            ) VALUES (1, ?, 'url', 'blocked', ?, '2026-04-05T00:00:00+00:00', ?)
            """,
            (source_url, f"{blocked_stage}:failed", flags),
        )
        conn.execute(
            """
            INSERT INTO cohort_file (
                id, cohort_id, asset_file_id, source_path,
                status, blocked_reason, blocked_stage, created_at
            ) VALUES (
                1, 1, 1, '/tmp/example.flac',
                'blocked', 'failed', ?, '2026-04-05T00:00:00+00:00'
            )
            """,
            (blocked_stage,),
        )
        conn.commit()
    finally:
        conn.close()


def _mark_complete(db_path: Path, cohort_id: int) -> None:
    """Transition a cohort and its files to complete state (used by fake flow stubs)."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            UPDATE cohort
            SET status = 'complete', blocked_reason = NULL,
                completed_at = '2026-04-05T01:00:00+00:00'
            WHERE id = ?
            """,
            (cohort_id,),
        )
        conn.execute(
            """
            UPDATE cohort_file
            SET status = 'ok', blocked_reason = NULL, blocked_stage = NULL
            WHERE cohort_id = ?
            """,
            (cohort_id,),
        )
        conn.execute(
            "UPDATE asset_file SET status = 'ok', blocked_reason = NULL WHERE id = 1"
        )
        conn.commit()
    finally:
        conn.close()


def _snapshot(db_path: Path) -> tuple[tuple[object, ...], tuple[object, ...], tuple[object, ...]]:
    conn = sqlite3.connect(str(db_path))
    try:
        cohort_row = conn.execute(
            "SELECT status, blocked_reason FROM cohort WHERE id = 1"
        ).fetchone()
        cohort_file_row = conn.execute(
            "SELECT status, blocked_reason, blocked_stage FROM cohort_file WHERE id = 1"
        ).fetchone()
        asset_row = conn.execute(
            "SELECT status, blocked_reason FROM asset_file WHERE id = 1"
        ).fetchone()
        assert cohort_row is not None
        assert cohort_file_row is not None
        assert asset_row is not None
        return tuple(cohort_row), tuple(cohort_file_row), tuple(asset_row)
    finally:
        conn.close()


def test_fix_and_get_fix_converge_to_identical_db_state(tmp_path: Path, monkeypatch) -> None:
    """
    Verify that `tagslut fix 1` and `tagslut get <url> --fix` produce identical
    DB state for the same blocked cohort.

    The seed uses blocked_stage='enrich' with dj=false/playlist=false.
    With per-stage re-entry, both paths route through _resume_late_stage
    → retag_flac_paths (mocked to succeed) → mark_paths_ok → complete.
    The convergence property holds because both entry points call the same
    resume_cohort() implementation.
    """
    source_url = "https://example.com/playlist/blocked"
    fix_db = tmp_path / "fix.db"
    get_db = tmp_path / "get_fix.db"
    _seed_blocked_cohort(fix_db, source_url=source_url)
    _seed_blocked_cohort(get_db, source_url=source_url)

    def _fake_retag(*, db_path, flac_paths, force):  # type: ignore[no-untyped-def]
        from tagslut.cli.commands._cohort_state import RetagResult
        return RetagResult(ok_paths=list(flac_paths), blocked={})

    monkeypatch.setattr("tagslut.cli.commands.fix.retag_flac_paths", _fake_retag)

    runner = CliRunner()
    fix_result = runner.invoke(cli, ["fix", "1", "--db", str(fix_db)])
    get_fix_result = runner.invoke(cli, ["get", source_url, "--fix", "--db", str(get_db)])

    assert fix_result.exit_code == 0, fix_result.output
    assert get_fix_result.exit_code == 0, get_fix_result.output
    assert _snapshot(fix_db) == _snapshot(get_db)


def test_fix_enrich_stage_skips_intake_calls_retag(tmp_path: Path, monkeypatch) -> None:
    """
    A cohort blocked at 'enrich' must call retag_flac_paths and must NOT
    invoke _run_url_flow, which would trigger a re-download.
    """
    source_url = "https://example.com/enrich-blocked"
    db_path = tmp_path / "enrich.db"
    _seed_blocked_cohort_at_stage(db_path, source_url=source_url, blocked_stage="enrich")

    def _must_not_call_intake(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("_run_url_flow must not be called for enrich-stage resume")

    monkeypatch.setattr("tagslut.cli.commands.get._run_url_flow", _must_not_call_intake)

    retag_called: list[bool] = []

    def _fake_retag(*, db_path, flac_paths, force):  # type: ignore[no-untyped-def]
        retag_called.append(True)
        from tagslut.cli.commands._cohort_state import RetagResult
        return RetagResult(ok_paths=list(flac_paths), blocked={})

    import tagslut.cli.commands._cohort_state as _cs

    monkeypatch.setattr(_cs, "retag_flac_paths", _fake_retag)
    monkeypatch.setattr(
        _cs,
        "build_output_artifacts",
        lambda **_kw: _cs.OutputResult(
            ok=True, stage=None, reason=None, mp3_paths=[], playlist_paths=[]
        ),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["fix", "1", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert retag_called, "retag_flac_paths must be called for enrich-stage resume"
    assert "Resume cohort 1" in result.output
    assert "blocked stage: enrich" in result.output
    assert "action: internal retag via Enricher" in result.output


def test_fix_mp3_stage_skips_retag_and_intake(tmp_path: Path, monkeypatch) -> None:
    """
    A cohort blocked at 'mp3' must invoke build_output_artifacts directly.
    Neither _run_url_flow nor retag_flac_paths should be called.

    Seed uses dj=true so build_output_artifacts is not short-circuited by
    the 'no output requested' guard in _resume_late_stage.
    """
    source_url = "https://example.com/mp3-blocked"
    db_path = tmp_path / "mp3.db"
    _seed_blocked_cohort_at_stage(
        db_path,
        source_url=source_url,
        blocked_stage="mp3",
        flags='{"command":"get","dj":true,"playlist":false}',
    )

    def _must_not_call_intake(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("_run_url_flow must not be called for mp3-stage resume")

    monkeypatch.setattr("tagslut.cli.commands.get._run_url_flow", _must_not_call_intake)

    import tagslut.cli.commands._cohort_state as _cs

    def _must_not_retag(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("retag_flac_paths must not be called for mp3-stage resume")

    monkeypatch.setattr(_cs, "retag_flac_paths", _must_not_retag)

    output_called: list[bool] = []

    def _fake_output(**kwargs):  # type: ignore[no-untyped-def]
        output_called.append(True)
        return _cs.OutputResult(
            ok=True, stage=None, reason=None, mp3_paths=[], playlist_paths=[]
        )

    monkeypatch.setattr(_cs, "build_output_artifacts", _fake_output)

    runner = CliRunner()
    result = runner.invoke(cli, ["fix", "1", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert output_called, "build_output_artifacts must be called for mp3-stage resume"


def test_fix_download_stage_uses_full_flow(tmp_path: Path, monkeypatch) -> None:
    """
    A cohort blocked at 'download' must re-run the full URL intake flow.
    retag_flac_paths must NOT be called.
    """
    source_url = "https://example.com/download-blocked"
    db_path = tmp_path / "download.db"
    _seed_blocked_cohort_at_stage(
        db_path,
        source_url=source_url,
        blocked_stage="download",
    )

    full_flow_called: list[bool] = []

    def _fake_run_url_flow(*, url, db_path, cohort_id, dj, mp3, playlist, raw_backend=False):  # type: ignore[no-untyped-def]
        full_flow_called.append(True)
        assert url == source_url
        assert mp3 is False
        assert raw_backend is True
        _mark_complete(db_path, cohort_id)
        return True, None

    monkeypatch.setattr("tagslut.cli.commands.get._run_url_flow", _fake_run_url_flow)

    import tagslut.cli.commands._cohort_state as _cs

    def _must_not_retag(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("retag_flac_paths must not be called for download-stage resume")

    monkeypatch.setattr(_cs, "retag_flac_paths", _must_not_retag)

    runner = CliRunner()
    result = runner.invoke(cli, ["fix", "1", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert full_flow_called, "_run_url_flow must be called for early-stage (download) resume"
    assert "Resume cohort 1" in result.output
    assert "blocked stage: download" in result.output
    assert "mode: raw verbose url resume" in result.output
    assert f"resume command: tagslut get {source_url} --tag --db {db_path}" in result.output


def test_fix_download_stage_preserves_mp3_flag(tmp_path: Path, monkeypatch) -> None:
    source_url = "https://example.com/download-mp3-blocked"
    db_path = tmp_path / "download-mp3.db"
    _seed_blocked_cohort_at_stage(
        db_path,
        source_url=source_url,
        blocked_stage="download",
        flags='{"command":"get","dj":false,"mp3":true,"playlist":false}',
    )

    captured: dict[str, object] = {}

    def _fake_run_url_flow(*, url, db_path, cohort_id, dj, mp3, playlist, raw_backend=False):  # type: ignore[no-untyped-def]
        captured.update(
            {
                "url": url,
                "db_path": db_path,
                "cohort_id": cohort_id,
                "dj": dj,
                "mp3": mp3,
                "playlist": playlist,
                "raw_backend": raw_backend,
            }
        )
        _mark_complete(db_path, cohort_id)
        return True, None

    monkeypatch.setattr("tagslut.cli.commands.get._run_url_flow", _fake_run_url_flow)

    runner = CliRunner()
    result = runner.invoke(cli, ["fix", "1", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert captured["url"] == source_url
    assert captured["dj"] is False
    assert captured["mp3"] is True
    assert captured["playlist"] is False
    assert captured["raw_backend"] is True


def test_fix_allows_stale_running_cohort_with_blocked_rows(tmp_path: Path, monkeypatch) -> None:
    source_url = "https://example.com/stale-running"
    db_path = tmp_path / "stale-running.db"
    _seed_blocked_cohort_at_stage(
        db_path,
        source_url=source_url,
        blocked_stage="download",
    )

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("UPDATE cohort SET status = 'running', blocked_reason = NULL WHERE id = 1")
        conn.commit()
    finally:
        conn.close()

    full_flow_called: list[bool] = []

    def _fake_run_url_flow(*, url, db_path, cohort_id, dj, mp3, playlist, raw_backend=False):  # type: ignore[no-untyped-def]
        full_flow_called.append(True)
        assert url == source_url
        assert raw_backend is True
        _mark_complete(db_path, cohort_id)
        return True, None

    monkeypatch.setattr("tagslut.cli.commands.get._run_url_flow", _fake_run_url_flow)

    runner = CliRunner()
    result = runner.invoke(cli, ["fix", "1", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert full_flow_called, "stale running cohort with blocked files must still resume"


def test_fix_qobuz_download_stage_reuses_existing_batch_root(tmp_path: Path, monkeypatch) -> None:
    source_url = "https://open.qobuz.com/album/test-album"
    db_path = tmp_path / "qobuz-download.db"
    batch_root = tmp_path / "StreamripDownloads" / "Qobuz"
    batch_root.mkdir(parents=True)
    (batch_root / "track.flac").write_bytes(b"flac")
    _seed_blocked_cohort_at_stage(
        db_path,
        source_url=source_url,
        blocked_stage="download",
    )

    captured: dict[str, object] = {}

    def _fake_run_url_flow(
        *,
        url,
        db_path,
        cohort_id,
        dj,
        mp3,
        playlist,
        existing_batch_root=None,
    ):  # type: ignore[no-untyped-def]
        captured.update(
            {
                "url": url,
                "db_path": db_path,
                "cohort_id": cohort_id,
                "existing_batch_root": existing_batch_root,
            }
        )
        _mark_complete(db_path, cohort_id)
        return True, None

    monkeypatch.setattr("tagslut.cli.commands.fix._existing_qobuz_batch_root", lambda _url: batch_root)
    monkeypatch.setattr("tagslut.cli.commands.get._run_url_flow", _fake_run_url_flow)

    runner = CliRunner()
    result = runner.invoke(cli, ["fix", "1", "--db", str(db_path)])

    assert result.exit_code == 0, result.output
    assert captured["url"] == source_url
    assert captured["existing_batch_root"] == batch_root
    assert "mode: staged qobuz batch reuse" in result.output
    assert f"--batch-root {batch_root}" in result.output
