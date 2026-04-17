from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import click

from tagslut.cli.commands._cohort_state import (
    bind_asset_paths,
    build_output_artifacts,
    cohort_requires_fix_message,
    create_cohort,
    ensure_cohort_support,
    find_latest_blocked_cohort_for_source,
    mark_paths_ok,
    mark_cohort_file_blocked,
    record_blocked_paths,
    refresh_cohort_status,
    resolve_flac_paths,
    retag_flac_paths,
    set_cohort_blocked,
)
from tagslut.cli.runtime import run_tagslut_wrapper
from tagslut.exec.intake_orchestrator import IntakeResult, run_intake
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path
from tagslut.utils.env_paths import get_artifacts_dir


def _looks_like_url(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _intake_paths(result: IntakeResult) -> list[Path]:
    for stage_name in ("enrich", "mp3"):
        stage = next((item for item in result.stages if item.stage == stage_name), None)
        if stage is None or stage.artifact_path is None or not stage.artifact_path.exists():
            continue
        if stage_name == "mp3":
            try:
                payload = json.loads(stage.artifact_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            raw_paths = payload.get("paths") if isinstance(payload, dict) else None
            if isinstance(raw_paths, list):
                return [
                    Path(str(raw)).expanduser().resolve()
                    for raw in raw_paths
                    if isinstance(raw, str)
                ]
            continue
        return [
            Path(line.strip()).expanduser().resolve()
            for line in stage.artifact_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    stage = next((item for item in result.stages if item.stage == "promote"), None)
    if stage is not None and stage.artifact_path is not None and stage.artifact_path.exists():
        return [
            Path(line.strip()).expanduser().resolve()
            for line in stage.artifact_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return []


def _first_failure(result: IntakeResult) -> tuple[str, str]:
    for stage in result.stages:
        if stage.status in {"failed", "blocked"}:
            detail = stage.detail or stage.status
            return stage.stage, detail
    return result.disposition, result.summary()


def _echo_failure_summary(result: IntakeResult) -> None:
    click.echo(result.summary())
    for stage in result.stages:
        if stage.status in {"failed", "blocked"}:
            detail = stage.detail or stage.status
            click.echo(f"{stage.stage}: {detail}", err=True)


def _cohort_flags(
    *,
    input_value: str,
    dj: bool,
    playlist: bool,
) -> dict[str, object]:
    return {
        "command": "get",
        "input": input_value,
        "dj": bool(dj),
        "playlist": bool(playlist),
    }


def _run_local_flow(
    *,
    input_path: Path,
    db_path: Path,
    cohort_id: int,
    dj: bool,
    playlist: bool,
) -> tuple[bool, str | None]:
    try:
        run_tagslut_wrapper(
            [
                "index",
                "register",
                str(input_path),
                "--source",
                "local_path",
                "--db",
                str(db_path),
                "--execute",
            ]
        )
    except SystemExit as exc:
        return False, f"register failed with exit {exc.code}"

    flac_paths = resolve_flac_paths(input_path)
    if not flac_paths:
        return False, "no FLAC inputs resolved from local path"

    with sqlite3.connect(str(db_path)) as conn:
        ensure_cohort_support(conn)
        bind_asset_paths(conn, cohort_id=cohort_id, paths=flac_paths)
        conn.commit()
        retag_result = retag_flac_paths(db_path=db_path, flac_paths=flac_paths, force=False)
        mark_paths_ok(conn, cohort_id=cohort_id, paths=retag_result.ok_paths)
        for path, reason in retag_result.blocked.items():
            asset_row = conn.execute(
                "SELECT id FROM asset_file WHERE path = ? LIMIT 1",
                (str(path),),
            ).fetchone()
            asset_file_id = int(asset_row[0]) if asset_row is not None and asset_row[0] is not None else None
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
                reason=f"{len(retag_result.blocked)} file(s) failed during enrich",
            )
            conn.commit()
            return False, "one or more files failed during enrich"

    output_result = build_output_artifacts(
        db_path=db_path,
        cohort_id=cohort_id,
        flac_paths=retag_result.ok_paths,
        dj=dj,
        playlist_only=playlist and not dj,
    )
    with sqlite3.connect(str(db_path)) as conn:
        ensure_cohort_support(conn)
        if not output_result.ok:
            record_blocked_paths(
                conn,
                cohort_id=cohort_id,
                stage=output_result.stage or "output",
                reason=output_result.reason or "output failed",
                paths=retag_result.ok_paths,
                placeholder_source=str(input_path),
            )
            conn.commit()
            return False, output_result.reason

        refresh_cohort_status(conn, cohort_id=cohort_id)
        conn.commit()
    return True, None


def _run_url_flow(
    *,
    url: str,
    db_path: Path,
    cohort_id: int,
    dj: bool,
    playlist: bool,
) -> tuple[bool, str | None]:
    artifact_dir = (get_artifacts_dir() / "intake").resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result = run_intake(
        url=url,
        db_path=db_path,
        tag=True,
        mp3=False,
        dj=False,
        dry_run=False,
        artifact_dir=artifact_dir,
        verbose=False,
        debug_raw=False,
        no_precheck=False,
        force_download=False,
    )
    flac_paths = _intake_paths(result)
    with sqlite3.connect(str(db_path)) as conn:
        ensure_cohort_support(conn)
        if flac_paths:
            bind_asset_paths(conn, cohort_id=cohort_id, paths=flac_paths)

        if result.disposition != "completed":
            stage, reason = _first_failure(result)
            record_blocked_paths(
                conn,
                cohort_id=cohort_id,
                stage=stage,
                reason=reason,
                paths=flac_paths,
                placeholder_source=url,
            )
            conn.commit()
            _echo_failure_summary(result)
            return False, reason

        mark_paths_ok(conn, cohort_id=cohort_id, paths=flac_paths)
        conn.commit()

    output_result = build_output_artifacts(
        db_path=db_path,
        cohort_id=cohort_id,
        flac_paths=flac_paths,
        dj=dj,
        playlist_only=playlist and not dj,
    )
    with sqlite3.connect(str(db_path)) as conn:
        ensure_cohort_support(conn)
        if not output_result.ok:
            record_blocked_paths(
                conn,
                cohort_id=cohort_id,
                stage=output_result.stage or "output",
                reason=output_result.reason or "output failed",
                paths=flac_paths,
                placeholder_source=url,
            )
            conn.commit()
            click.echo(result.summary())
            click.echo(f"{output_result.stage or 'output'}: {output_result.reason}", err=True)
            return False, output_result.reason

        refresh_cohort_status(conn, cohort_id=cohort_id)
        conn.commit()

    click.echo(result.summary())
    return True, None


def register_get_command(cli: click.Group) -> None:
    @cli.command(
        "get",
        help=(
            "Download and ingest a provider URL or local path. "
            "Runs precheck → download → tag → promote → M3U. "
            "Add --dj to build MP3 output with DJ playlists, "
            "--fix to resume a blocked cohort."
        ),
    )
    @click.argument("input_value")
    @click.option("--db", "db_path_arg", type=click.Path(), help="Database path (or TAGSLUT_DB)")
    @click.option("--dj", is_flag=True, help="Build MP3 output with DJ playlists.")
    @click.option("--playlist", is_flag=True, help="Emit M3U only; does not imply --dj.")
    @click.option("--fix", "fix_mode", is_flag=True, help="Resume the most recent blocked cohort for this source.")
    def get_command(  # type: ignore[misc]
        input_value: str,
        db_path_arg: str | None,
        dj: bool,
        playlist: bool,
        fix_mode: bool,
    ) -> None:
        from tagslut.cli.commands.fix import resume_source

        try:
            resolution = resolve_cli_env_db_path(db_path_arg, purpose="write", source_label="--db")
        except DbResolutionError as exc:
            raise click.ClickException(str(exc)) from exc
        db_path = resolution.path

        if _looks_like_url(input_value):
            source_value = input_value.strip()
            with sqlite3.connect(str(db_path)) as conn:
                ensure_cohort_support(conn)
                if fix_mode:
                    status_code = resume_source(
                        conn=conn,
                        db_path=db_path,
                        source_url=source_value,
                    )
                    conn.commit()
                    raise SystemExit(status_code)

                blocked_row, ambiguous = find_latest_blocked_cohort_for_source(
                    conn,
                    source_url=source_value,
                )
                if blocked_row is not None and not ambiguous:
                    click.echo(
                        cohort_requires_fix_message(
                            cohort_id=int(blocked_row[0]),
                            source_url=str(blocked_row[1]) if blocked_row[1] is not None else None,
                        ),
                        err=True,
                    )
                cohort_id = create_cohort(
                    conn,
                    source_url=source_value,
                    source_kind="url",
                    flags=_cohort_flags(input_value=source_value, dj=dj, playlist=playlist),
                )
                conn.commit()

            ok, reason = _run_url_flow(
                url=source_value,
                db_path=db_path,
                cohort_id=cohort_id,
                dj=dj,
                playlist=playlist,
            )
            raise SystemExit(0 if ok else 2)

        input_path = Path(input_value).expanduser().resolve()
        if fix_mode:
            raise click.ClickException(
                "--fix is not valid on a local path. Use tagslut fix <cohort_id> or tagslut get <url> --fix to resume a remote cohort."
            )
        if not input_path.exists():
            raise click.ClickException(f"Path not found: {input_path}")

        with sqlite3.connect(str(db_path)) as conn:
            ensure_cohort_support(conn)
            blocked_row, ambiguous = find_latest_blocked_cohort_for_source(
                conn,
                source_url=str(input_path),
            )
            if blocked_row is not None and not ambiguous:
                click.echo(
                    cohort_requires_fix_message(
                        cohort_id=int(blocked_row[0]),
                        source_url=str(blocked_row[1]) if blocked_row[1] is not None else None,
                    ),
                    err=True,
                )
            cohort_id = create_cohort(
                conn,
                source_url=str(input_path),
                source_kind="local_path",
                flags=_cohort_flags(input_value=str(input_path), dj=dj, playlist=playlist),
            )
            conn.commit()

        ok, reason = _run_local_flow(
            input_path=input_path,
            db_path=db_path,
            cohort_id=cohort_id,
            dj=dj,
            playlist=playlist,
        )
        if not ok:
            click.echo(reason or "local get failed", err=True)
        raise SystemExit(0 if ok else 2)
