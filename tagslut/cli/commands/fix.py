from __future__ import annotations

import os
import shlex
import sqlite3
from pathlib import Path

import click

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
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

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


def _shell_join(parts: list[object]) -> str:
    return shlex.join([str(part) for part in parts])


def _resume_outputs(*, dj: bool, mp3: bool, playlist: bool) -> str:
    outputs: list[str] = []
    if dj:
        outputs.append("dj")
    elif mp3:
        outputs.append("mp3")
    if playlist:
        outputs.append("playlist")
    if not outputs:
        outputs.append("flac")
    return ", ".join(outputs)


def _echo_resume_banner(
    *,
    cohort_id: int,
    source_kind: str,
    source_url: str,
    min_stage: str | None,
    dj: bool,
    mp3: bool,
    playlist: bool,
) -> None:
    click.echo(f"Resume cohort {cohort_id}")
    click.echo(f"  source: {source_url or '(unknown source)'}")
    click.echo(f"  kind: {source_kind}")
    click.echo(f"  blocked stage: {min_stage or 'unknown'}")
    click.echo(f"  outputs: {_resume_outputs(dj=dj, mp3=mp3, playlist=playlist)}")


def _echo_early_resume_plan(
    *,
    source_kind: str,
    source_url: str,
    db_path: Path,
    dj: bool,
    mp3: bool,
    playlist: bool,
    existing_batch_root: Path | None,
) -> None:
    if source_kind == "url":
        if existing_batch_root is not None:
            click.echo("  mode: staged qobuz batch reuse")
            click.echo(
                "  backend: "
                + _shell_join(
                    [
                        "tools/get-intake",
                        "--verbose",
                        "--source",
                        "qobuz",
                        "--missing-policy",
                        "download",
                        "--execute",
                        "--m3u",
                        "--url",
                        source_url,
                        "--no-download",
                        "--batch-root",
                        existing_batch_root,
                        "--db",
                        db_path,
                    ]
                )
            )
            return
        click.echo("  mode: raw verbose url resume")
        cmd: list[object] = ["tagslut", "get", source_url, "--tag"]
        if mp3:
            cmd.append("--mp3")
        if dj:
            cmd.append("--dj")
        if playlist:
            cmd.append("--playlist")
        cmd.extend(["--db", db_path])
        click.echo(f"  resume command: {_shell_join(cmd)}")
        return

    input_path = Path(source_url).expanduser().resolve()
    click.echo(
        "  register command: "
        + _shell_join(
            [
                "tagslut",
                "index",
                "register",
                input_path,
                "--source",
                "local_path",
                "--db",
                db_path,
                "--execute",
            ]
        )
    )
    click.echo("  next: internal retag + output rebuild")


def _echo_late_resume_plan(
    *,
    min_stage: str,
    flac_paths: list[Path],
    dj: bool,
    mp3: bool,
    playlist: bool,
) -> None:
    click.echo(f"  re-enter: {min_stage}")
    click.echo(f"  paths: {len(flac_paths)} flac")
    if min_stage == "enrich":
        click.echo("  action: internal retag via Enricher providers=beatport,tidal,qobuz")
    if dj:
        click.echo("  action: build tagged mp3 assets + dj playlists")
    elif mp3:
        click.echo("  action: rebuild tagged mp3 assets")
    elif playlist:
        click.echo("  action: rebuild merged m3u from cohort flacs")
    else:
        click.echo("  action: mark cohort paths ok")


def _existing_qobuz_batch_root(source_url: str) -> Path | None:
    if "qobuz.com" not in (source_url or "").strip().lower():
        return None
    streamrip_root = os.environ.get("STREAMRIP_ROOT")
    if streamrip_root:
        root = Path(streamrip_root).expanduser().resolve() / "Qobuz"
    else:
        staging_root = os.environ.get("STAGING_ROOT") or os.environ.get("VOLUME_STAGING")
        if staging_root:
            root = Path(staging_root).expanduser().resolve() / "StreamripDownloads" / "Qobuz"
        else:
            root = Path("/Volumes/MUSIC/staging/StreamripDownloads/Qobuz")
    if not root.exists():
        return None
    if next(root.rglob("*.flac"), None) is None:
        return None
    return root


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


def _resume_late_stage(
    *,
    conn: sqlite3.Connection,
    db_path: Path,
    cohort_id: int,
    min_stage: str,
    dj: bool,
    mp3: bool,
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

    _echo_late_resume_plan(
        min_stage=min_stage,
        flac_paths=flac_paths,
        dj=dj,
        mp3=mp3,
        playlist=playlist,
    )

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


def retag_flac_paths(*, db_path: Path, flac_paths: list[Path], force: bool) -> object:
    import tagslut.cli.commands._cohort_state as _cs

    return _cs.retag_flac_paths(db_path=db_path, flac_paths=flac_paths, force=force)


def build_output_artifacts(
    *,
    db_path: Path,
    cohort_id: int,
    flac_paths: list[Path],
    dj: bool,
    playlist_only: bool,
) -> object:
    import tagslut.cli.commands._cohort_state as _cs

    return _cs.build_output_artifacts(
        db_path=db_path,
        cohort_id=cohort_id,
        flac_paths=flac_paths,
        dj=dj,
        playlist_only=playlist_only,
    )


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
    blocked = blocked_rows_for_cohort(conn, cohort_id=cohort_id)
    status = str(row[3])
    stale_running = status == "running" and bool(blocked)
    if status != "blocked" and not stale_running:
        click.echo(f"Cohort {cohort_id} is not blocked.", err=True)
        return 1

    source_url = str(row[1]) if row[1] is not None else ""
    source_kind = str(row[2])
    flags = decode_flags(str(row[7]) if row[7] is not None else None)
    dj = bool(flags.get("dj"))
    mp3 = bool(flags.get("mp3"))
    playlist = bool(flags.get("playlist"))

    min_stage = _min_blocked_stage(blocked)
    _echo_resume_banner(
        cohort_id=cohort_id,
        source_kind=source_kind,
        source_url=source_url,
        min_stage=min_stage,
        dj=dj,
        mp3=mp3,
        playlist=playlist,
    )

    set_cohort_running(conn, cohort_id=cohort_id)
    conn.commit()

    # Early-stage failure: FLACs not yet on disk. Re-run the full flow.
    if min_stage is None or min_stage in EARLY_BLOCKED_STAGES:
        if source_kind == "url":
            existing_batch_root = _existing_qobuz_batch_root(source_url)
            _echo_early_resume_plan(
                source_kind=source_kind,
                source_url=source_url,
                db_path=db_path,
                dj=dj,
                mp3=mp3,
                playlist=playlist,
                existing_batch_root=existing_batch_root,
            )
            flow_kwargs = {
                "url": source_url,
                "db_path": db_path,
                "cohort_id": cohort_id,
                "dj": dj,
                "mp3": mp3,
                "playlist": playlist,
            }
            if existing_batch_root is not None:
                flow_kwargs["existing_batch_root"] = existing_batch_root
            else:
                flow_kwargs["raw_backend"] = True
            ok, _reason = _run_url_flow(**flow_kwargs)
            return 0 if ok else 2
        input_path = Path(source_url).expanduser().resolve()
        _echo_early_resume_plan(
            source_kind=source_kind,
            source_url=source_url,
            db_path=db_path,
            dj=dj,
            mp3=mp3,
            playlist=playlist,
            existing_batch_root=None,
        )
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
        mp3=mp3,
        playlist=playlist,
    )


def resume_source(
    *,
    conn: sqlite3.Connection,
    db_path: Path,
    source_url: str,
) -> int:
    ensure_cohort_support(conn)
    row, ambiguous = find_latest_blocked_cohort_for_source(conn, source_url=source_url)
    if row is None:
        click.echo(f"No blocked cohort exists for: {source_url}", err=True)
        return 1
    if ambiguous:
        click.echo(
            "Multiple blocked cohorts match this exact URL. Use `tagslut fix <cohort_id>`.",
            err=True,
        )
        return 1
    return resume_cohort(conn=conn, db_path=db_path, cohort_id=int(row[0]))


def _print_blocked_list(rows: list[sqlite3.Row | tuple[object, ...]]) -> None:
    if not rows:
        click.echo("No blocked cohorts found.")
        return
    for row in rows:
        blocked_count = int(row[6] or 0)
        source = str(row[1]) if row[1] is not None else "(unknown source)"
        reason = str(row[4]) if row[4] is not None else "(no reason)"
        click.echo(f"{row[0]}  {source}  blocked={blocked_count}  {reason}")


def register_fix_command(cli: click.Group) -> None:
    @cli.command("fix", help="Resume a blocked cohort or repair a specific file or identity.")
    @click.argument("cohort_id", required=False, type=int)
    @click.option("--db", "db_path_arg", type=click.Path(), help="Database path (or TAGSLUT_DB)")
    def fix_command(cohort_id: int | None, db_path_arg: str | None) -> None:  # type: ignore[misc]
        try:
            resolution = resolve_cli_env_db_path(db_path_arg, purpose="write", source_label="--db")
        except DbResolutionError as exc:
            raise click.ClickException(str(exc)) from exc
        db_path = resolution.path

        with sqlite3.connect(str(db_path)) as conn:
            ensure_cohort_support(conn)
            if cohort_id is None:
                rows = list_blocked_cohorts(conn)
                _print_blocked_list(rows)
                status_code = 0
                for row in rows:
                    click.echo(f"Resuming cohort {row[0]}...")
                    code = resume_cohort(conn=conn, db_path=db_path, cohort_id=int(row[0]))
                    if code != 0:
                        status_code = code
                conn.commit()
                raise SystemExit(status_code)

            code = resume_cohort(conn=conn, db_path=db_path, cohort_id=int(cohort_id))
            conn.commit()
            raise SystemExit(code)
