# fix(fix): implement per-stage re-entry in resume_cohort

## DO NOT recreate existing files

The following files already exist. Only edit the specific sections called out below. Do not delete or recreate them:

- `tagslut/cli/commands/fix.py`
- `tests/cli/test_fix_convergence.py`

The following files must NOT be touched at all:

- `tagslut/cli/commands/get.py`
- `tagslut/cli/commands/_cohort_state.py`
- `tagslut/cli/main.py`
- `tagslut/storage/v3/migrations/0018_blocked_cohort_state.sql`

---

## Problem

`resume_cohort` in `fix.py` currently re-runs the entire intake flow for every blocked cohort regardless of where it failed.

A cohort blocked at `enrich` triggers a full re-download.
A cohort blocked at `mp3` re-downloads and re-enriches.

This violates the recovery contract.

`cohort_file.blocked_stage` already stores the stage at which each file failed.
`resume_cohort` must use that information to re-enter at the correct point.

---

## Stage ordering

Add this constant at module level in `fix.py`, immediately after the imports:

```python
_STAGE_ORDER: tuple[str, ...] = (
    "resolve",
    "precheck",
    "download",
    "acquisition",
    "enrich",
    "mp3",
    "transcode",
    "playlist",
    "m3u",
)


⸻

New imports required in fix.py

Replace the existing import block from tagslut.cli.commands._cohort_state with:

from tagslut.cli.commands._cohort_state import (
    EARLY_BLOCKED_STAGES,
    blocked_rows_for_cohort,
    build_output_artifacts,
    cohort_paths,
    decode_flags,
    ensure_cohort_support,
    find_latest_blocked_cohort_for_source,
    get_cohort,
    list_blocked_cohorts,
    mark_cohort_file_blocked,
    mark_paths_ok,
    record_blocked_paths,
    refresh_cohort_status,
    retag_flac_paths,
    set_cohort_blocked,
    set_cohort_running,
)

EARLY_BLOCKED_STAGES is already defined in _cohort_state.py as:

frozenset({"resolve", "precheck", "download", "acquisition"})


⸻

Add _min_blocked_stage() to fix.py

Insert this immediately after _STAGE_ORDER:

def _min_blocked_stage(blocked_rows: list) -> str | None:
    """
    Return the earliest stage at which any cohort_file is blocked,
    using _STAGE_ORDER for ordering.

    Rows with NULL or unrecognised blocked_stage are treated as index 0
    (the earliest possible stage). This is conservative and forces a full re-run.

    Returns None when blocked_rows is empty.

    cohort_file row positional fields:
      0  id
      1  cohort_id
      2  asset_file_id
      3  source_path
      4  status
      5  blocked_reason
      6  blocked_stage
      7  created_at
    """
    if not blocked_rows:
        return None
    positions: list[int] = []
    for row in blocked_rows:
        stage = row[6]
        if stage is None or stage not in _STAGE_ORDER:
            positions.append(0)
        else:
            positions.append(_STAGE_ORDER.index(stage))
    return _STAGE_ORDER[min(positions)]


⸻

Add _resume_late_stage() to fix.py

Insert this immediately after _min_blocked_stage:

def _resume_late_stage(
    *,
    conn: sqlite3.Connection,
    db_path: Path,
    cohort_id: int,
    min_stage: str,
    dj: bool,
    playlist: bool,
) -> int:
    """
    Re-enter the pipeline at `min_stage` for a cohort whose FLACs already
    exist on disk. Does NOT re-download or re-register.

    Dispatch table:
      enrich              -> retag_flac_paths, then build_output_artifacts
                             only when dj or playlist output is requested
      mp3 / transcode     -> build_output_artifacts only
                             when dj or playlist output is requested
      playlist / m3u      -> build_output_artifacts only
                             when dj or playlist output is requested

    If neither dj nor playlist is requested, late-stage resume completes after
    successful re-enrich or path validation without building output artifacts.
    """
    _ENRICH_STAGES = frozenset({"enrich"})

    flac_paths = cohort_paths(conn, cohort_id=cohort_id)
    if not flac_paths:
        click.echo(
            f"Cohort {cohort_id}: no FLAC paths recoverable — "
            "cannot re-enter at late stage. Re-run from source.",
            err=True,
        )
        set_cohort_blocked(
            conn,
            cohort_id=cohort_id,
            reason="no flac paths for late-stage resume",
        )
        conn.commit()
        return 2

    if min_stage in _ENRICH_STAGES:
        retag_result = retag_flac_paths(
            db_path=db_path,
            flac_paths=flac_paths,
            force=False,
        )
        mark_paths_ok(conn, cohort_id=cohort_id, paths=retag_result.ok_paths)
        for path, reason in retag_result.blocked.items():
            asset_row = conn.execute(
                "SELECT id FROM asset_file WHERE path = ? LIMIT 1",
                (str(path),),
            ).fetchone()
            asset_file_id = (
                int(asset_row[0])
                if asset_row is not None and asset_row[0] is not None
                else None
            )
            mark_cohort_file_blocked(
                conn,
                cohort_id=cohort_id,
                stage="enrich",
                reason=reason,
                source_path=str(path),
                asset_file_id=asset_file_id,
            )
        if retag_result.blocked:
            set_cohort_blocked(
                conn,
                cohort_id=cohort_id,
                reason=f"{len(retag_result.blocked)} file(s) still blocked after re-enrich",
            )
            conn.commit()
            return 2
        effective_paths = retag_result.ok_paths
    else:
        # mp3 / transcode / playlist / m3u: FLACs are already enriched
        effective_paths = flac_paths

    if not (dj or playlist):
        # No output artifacts requested — pipeline is complete
        mark_paths_ok(conn, cohort_id=cohort_id, paths=effective_paths)
        refresh_cohort_status(conn, cohort_id=cohort_id)
        conn.commit()
        return 0

    output_result = build_output_artifacts(
        db_path=db_path,
        cohort_id=cohort_id,
        flac_paths=effective_paths,
        dj=dj,
        playlist_only=playlist and not dj,
    )
    if not output_result.ok:
        record_blocked_paths(
            conn,
            cohort_id=cohort_id,
            stage=output_result.stage or "output",
            reason=output_result.reason or "output failed",
            paths=effective_paths,
            placeholder_source=f"cohort-{cohort_id}",
        )
        conn.commit()
        click.echo(
            f"{output_result.stage or 'output'}: {output_result.reason}",
            err=True,
        )
        return 2

    refresh_cohort_status(conn, cohort_id=cohort_id)
    conn.commit()
    return 0


⸻

Rewrite resume_cohort() in fix.py

Replace the current function body only.
Do not change the function signature.

def resume_cohort(
    *,
    conn: sqlite3.Connection,
    db_path: Path,
    cohort_id: int,
) -> int:
    from tagslut.cli.commands.get import _run_local_flow, _run_url_flow

    ensure_cohort_support(conn)
    row = get_cohort(conn, cohort_id)
    if row is None:
        click.echo(f"Blocked cohort not found: {cohort_id}", err=True)
        return 1
    if str(row[3]) != "blocked":
        click.echo(f"Cohort {cohort_id} is not blocked.", err=True)
        return 1

    source_url = str(row[1]) if row[1] is not None else ""
    source_kind = str(row[2])
    flags = decode_flags(str(row[7]) if row[7] is not None else None)
    dj = bool(flags.get("dj"))
    playlist = bool(flags.get("playlist"))

    blocked = blocked_rows_for_cohort(conn, cohort_id=cohort_id)
    min_stage = _min_blocked_stage(blocked)

    set_cohort_running(conn, cohort_id=cohort_id)
    conn.commit()

    # Early-stage failure: FLACs not yet on disk. Re-run the full flow.
    if min_stage is None or min_stage in EARLY_BLOCKED_STAGES:
        if source_kind == "url":
            ok, _reason = _run_url_flow(
                url=source_url,
                db_path=db_path,
                cohort_id=cohort_id,
                dj=dj,
                playlist=playlist,
            )
            return 0 if ok else 2
        input_path = Path(source_url).expanduser().resolve()
        ok, _reason = _run_local_flow(
            input_path=input_path,
            db_path=db_path,
            cohort_id=cohort_id,
            dj=dj,
            playlist=playlist,
        )
        return 0 if ok else 2

    # Late-stage failure: FLACs are on disk. Re-enter at the blocked stage.
    return _resume_late_stage(
        conn=conn,
        db_path=db_path,
        cohort_id=cohort_id,
        min_stage=min_stage,
        dj=dj,
        playlist=playlist,
    )


⸻

Required changes to tests/cli/test_fix_convergence.py

Add seed helpers after the existing _seed_blocked_cohort function

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

Add these three new tests after test_fix_and_get_fix_converge_to_identical_db_state

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

    def _fake_run_url_flow(*, url, db_path, cohort_id, dj, playlist):  # type: ignore[no-untyped-def]
        full_flow_called.append(True)
        assert url == source_url
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


⸻

Invariants
	1.	If any blocked file has blocked_stage in ('resolve', 'precheck', 'download', 'acquisition'), the cohort must take the full-flow path using _run_url_flow or _run_local_flow. retag_flac_paths must not be called.
	2.	If all blocked files are at enrich, the cohort must call retag_flac_paths and then call build_output_artifacts only when dj or playlist output is requested. _run_url_flow must not be called.
	3.	If all blocked files are at mp3 or transcode, the cohort must call build_output_artifacts only. Neither _run_url_flow nor retag_flac_paths may be called.
	4.	If all blocked files are at playlist or m3u, the same path as mp3 / transcode applies.
	5.	For mixed early and late blocked stages, the minimum stage wins. This is the conservative and correct choice.
	6.	cohort_paths() must be called only for late-stage re-entry.
	7.	set_cohort_running must be called on the outer conn and committed before any downstream flow function opens its own connection. Do not reorder this.
	8.	The existing test_fix_and_get_fix_converge_to_identical_db_state must continue to pass unchanged. Do not modify it.

⸻

Commit message

fix(fix): re-enter resume_cohort at blocked_stage instead of full flow

Reads blocked_stage from cohort_file rows, finds the minimum (earliest)
stage across all failed files, and re-enters the pipeline at that point.

Early failures (resolve, precheck, download, acquisition): full flow
unchanged — FLACs are not on disk.

Late failures:
  enrich          -> retag_flac_paths + build_output_artifacts
  mp3 / transcode -> build_output_artifacts only
  playlist / m3u  -> build_output_artifacts only

Adds _min_blocked_stage() and _resume_late_stage() to fix.py.
Adds three targeted tests to test_fix_convergence.py.


⸻

Run after completion

Run only:

poetry run pytest tests/cli/test_fix_convergence.py -v

Do not run the full test suite.
