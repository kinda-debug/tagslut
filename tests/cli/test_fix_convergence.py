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
    source_url = "https://example.com/playlist/blocked"
    fix_db = tmp_path / "fix.db"
    get_db = tmp_path / "get_fix.db"
    _seed_blocked_cohort(fix_db, source_url=source_url)
    _seed_blocked_cohort(get_db, source_url=source_url)

    def _fake_run_url_flow(*, url, db_path, cohort_id, dj, playlist):  # type: ignore[no-untyped-def]
        assert url == source_url
        assert cohort_id == 1
        assert dj is False
        assert playlist is False
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "UPDATE cohort SET status = 'complete', blocked_reason = NULL, completed_at = '2026-04-05T01:00:00+00:00' WHERE id = ?",
                (cohort_id,),
            )
            conn.execute(
                "UPDATE cohort_file SET status = 'ok', blocked_reason = NULL, blocked_stage = NULL WHERE cohort_id = ?",
                (cohort_id,),
            )
            conn.execute(
                "UPDATE asset_file SET status = 'ok', blocked_reason = NULL WHERE id = 1"
            )
            conn.commit()
        finally:
            conn.close()
        return True, None

    monkeypatch.setattr("tagslut.cli.commands.get._run_url_flow", _fake_run_url_flow)

    runner = CliRunner()
    fix_result = runner.invoke(cli, ["fix", "1", "--db", str(fix_db)])
    get_fix_result = runner.invoke(cli, ["get", source_url, "--fix", "--db", str(get_db)])

    assert fix_result.exit_code == 0, fix_result.output
    assert get_fix_result.exit_code == 0, get_fix_result.output
    assert _snapshot(fix_db) == _snapshot(get_db)
