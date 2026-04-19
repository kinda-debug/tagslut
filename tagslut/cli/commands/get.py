from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
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
from tagslut.cli.commands._index_helpers import write_m3u
from tagslut.cli.runtime import run_tagslut_wrapper
from tagslut.exec.dj_pool_m3u import write_dj_pool_m3u
from tagslut.exec.intake_orchestrator import IntakeResult, IntakeStageResult, run_intake
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path
from tagslut.utils.env_paths import get_artifacts_dir

_AUDIO_EXTENSIONS = {".flac", ".wav", ".aiff", ".aif", ".mp3", ".m4a", ".aac"}
_DEFAULT_MP3_LIBRARY = Path("/Volumes/MUSIC/MP3_LIBRARY")


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


def _latest_promoted_flacs_artifact(*, run_started: float) -> Path | None:
    compare_dir = (get_artifacts_dir() / "compare").resolve()
    if not compare_dir.exists():
        return None
    threshold = float(run_started) - 1.0
    for path in sorted(
        compare_dir.glob("promoted_flacs_*.txt"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        if path.stat().st_mtime >= threshold:
            return path.resolve()
    return None


def _resolve_qobuz_release_name(url: str) -> str | None:
    url = (url or "").strip()
    if "qobuz.com" not in url:
        return None
    entity = None
    qobuz_id = None
    if "/album/" in url:
        entity = "album"
        qobuz_id = url.rsplit("/album/", 1)[-1].split("?", 1)[0].strip("/")
    elif "/playlist/" in url:
        entity = "playlist"
        qobuz_id = url.rsplit("/playlist/", 1)[-1].split("?", 1)[0].strip("/")
    if not entity or not qobuz_id:
        return None
    try:
        import requests

        from tagslut.metadata.auth import TokenManager

        tm = TokenManager()
        app_id, _ = tm.get_qobuz_app_credentials()
        token = tm.ensure_qobuz_token()
        response = requests.get(
            f"https://www.qobuz.com/api.json/0.2/{entity}/get",
            params={f"{entity}_id": qobuz_id, "app_id": app_id},
            headers={"X-App-Id": app_id, "X-User-Auth-Token": token},
            timeout=8,
        )
        payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    title = payload.get("name") if entity == "playlist" else payload.get("title")
    if not isinstance(title, str):
        return None
    title = title.strip()
    return title or None


def _run_existing_qobuz_batch_flow(
    *,
    url: str,
    db_path: Path,
    batch_root: Path,
    run_started: float,
) -> IntakeResult:
    repo_root = Path(__file__).resolve().parents[3]
    get_intake = (repo_root / "tools" / "get-intake").resolve()
    cmd = [str(get_intake), "--verbose"]
    cmd.extend(
        [
            "--source",
            "qobuz",
            "--missing-policy",
            "download",
            "--execute",
            "--m3u",
            "--url",
            url,
            "--no-download",
            "--batch-root",
            str(batch_root),
            "--db",
            str(db_path),
        ]
    )
    playlist_name = _resolve_qobuz_release_name(url)
    if playlist_name:
        cmd.extend(["--playlist-name", playlist_name])

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    try:
        subprocess.run(cmd, check=True, cwd=str(repo_root), env=env)
    except subprocess.CalledProcessError as exc:
        return IntakeResult(
            url=url,
            stages=[
                IntakeStageResult(
                    stage="download",
                    status="failed",
                    detail=f"Download subprocess failed: exit {exc.returncode}",
                )
            ],
            disposition="failed",
            precheck_summary={},
            precheck_csv=None,
            artifact_path=None,
        )

    promoted_artifact = _latest_promoted_flacs_artifact(run_started=run_started)
    if promoted_artifact is None:
        return IntakeResult(
            url=url,
            stages=[
                IntakeStageResult(stage="download", status="ok"),
                IntakeStageResult(
                    stage="promote",
                    status="failed",
                    detail="Promoted FLAC artifact missing after Qobuz batch resume",
                ),
            ],
            disposition="failed",
            precheck_summary={},
            precheck_csv=None,
            artifact_path=None,
        )

    return IntakeResult(
        url=url,
        stages=[
            IntakeStageResult(stage="download", status="ok"),
            IntakeStageResult(
                stage="promote",
                status="ok",
                artifact_path=promoted_artifact,
            ),
        ],
        disposition="completed",
        precheck_summary={},
        precheck_csv=None,
        artifact_path=None,
    )


def _echo_failure_summary(result: IntakeResult) -> None:
    click.echo(result.summary())
    for stage in result.stages:
        if stage.status in {"failed", "blocked"}:
            detail = stage.detail or stage.status
            click.echo(f"{stage.stage}: {detail}", err=True)


def _echo_stage_details(result: IntakeResult, *, playlist_paths: list[Path] | None = None) -> None:
    click.echo("Stages:")
    for stage in result.stages:
        label = stage.stage.replace("_", " ")
        status = stage.status.upper().ljust(7)
        detail = f": {stage.detail}" if stage.detail else ""
        click.echo(f"  {status} {label}{detail}")
    for playlist_path in playlist_paths or []:
        click.echo(f"  OK      playlist: {playlist_path.name}")


def _cohort_flags(
    *,
    input_value: str,
    dj: bool,
    mp3: bool,
    playlist: bool,
) -> dict[str, object]:
    return {
        "command": "get",
        "input": input_value,
        "dj": bool(dj),
        "mp3": bool(mp3),
        "playlist": bool(playlist),
    }


def _is_audio_root(root: Path) -> bool:
    if not root.is_dir():
        return False
    return any(
        path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS
        for path in root.rglob("*")
    )


def _looks_like_spotiflacnext(root: Path) -> bool:
    if not root.is_dir():
        return False
    report_files = sorted(root.glob("*.txt"))
    if not report_files:
        return False
    try:
        first_line = report_files[0].read_text(encoding="utf-8").splitlines()[0].strip()
    except Exception:
        return False
    return first_line.startswith("Download Report")


def _detect_stage_source(root: Path) -> str | None:
    resolved_root = root.expanduser().resolve()
    base = resolved_root.name
    parent = resolved_root.parent.name

    for candidate in (base, parent):
        if candidate == "bpdl":
            return "bpdl"
        if candidate == "tidal":
            return "tidal"
        if candidate in {"StreamripDownloads", "Qobuz"}:
            return "qobuz"
        if candidate == "SpotiFLAC":
            return "legacy"

    if base == "SpotiFLACnext":
        return "spotiflacnext" if _looks_like_spotiflacnext(resolved_root) else "legacy"
    if parent == "SpotiFLACnext":
        return "spotiflacnext" if _looks_like_spotiflacnext(resolved_root) else "legacy"
    if _looks_like_spotiflacnext(resolved_root):
        return "spotiflacnext"
    if _is_audio_root(resolved_root):
        return "legacy"
    return None


def _run_local_stage_flow(*, input_path: Path, db_path: Path) -> tuple[bool, str | None]:
    if not input_path.is_dir():
        return False, "--tag requires a directory root"

    source = _detect_stage_source(input_path)
    if source is None:
        return False, f"cannot infer staged source from root: {input_path}"

    try:
        run_tagslut_wrapper(
            [
                "admin",
                "intake",
                "stage",
                str(input_path),
                "--source",
                source,
                "--db",
                str(db_path),
            ]
        )
    except SystemExit as exc:
        return False, f"stage failed with exit {exc.code}"

    return True, None


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


def _read_stage_paths(result: IntakeResult, *, stage_name: str) -> list[Path]:
    stage = next((item for item in result.stages if item.stage == stage_name), None)
    if stage is None or stage.artifact_path is None or not stage.artifact_path.exists():
        return []
    try:
        payload = json.loads(stage.artifact_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw_paths = payload.get("paths") if isinstance(payload, dict) else None
    if not isinstance(raw_paths, list):
        return []
    return [
        Path(str(raw)).expanduser().resolve()
        for raw in raw_paths
        if isinstance(raw, str)
    ]


def _common_parent_dir(paths: list[Path]) -> Path:
    if not paths:
        raise ValueError("paths must not be empty")
    if len(paths) == 1:
        return paths[0].resolve().parent
    return Path(os.path.commonpath([str(path.resolve()) for path in paths])).resolve()


def _candidate_m3u_dirs() -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    for raw in (
        os.environ.get("M3U_DIR"),
        os.environ.get("PLAYLIST_ROOT"),
        os.environ.get("TAGSLUT_PLAYLIST_ROOT"),
        os.environ.get("LIBRARY_ROOT"),
        os.environ.get("VOLUME_LIBRARY"),
        os.environ.get("MASTER_LIBRARY"),
    ):
        if not raw:
            continue
        path = Path(raw).expanduser().resolve()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(path)
    return candidates


def _latest_run_playlist_name(*, run_started: float) -> str | None:
    newest: tuple[float, str] | None = None
    threshold = float(run_started) - 1.0
    for directory in _candidate_m3u_dirs():
        if not directory.exists() or not directory.is_dir():
            continue
        for path in directory.glob("*.m3u"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < threshold:
                continue
            stem = (path.stem or "").strip()
            if not stem:
                continue
            if newest is None or mtime > newest[0]:
                newest = (mtime, stem)
    return newest[1] if newest is not None else None


def _fallback_mp3_playlist_name(*, mp3_paths: list[Path], mp3_root: Path) -> str | None:
    if not mp3_paths:
        return None
    common_dir = _common_parent_dir(mp3_paths)
    if common_dir == mp3_root.resolve():
        return None
    name = (common_dir.name or "").strip()
    return name or None


def _resolve_url_mp3_paths(*, result: IntakeResult, mp3_root: Path) -> list[Path]:
    from tagslut.exec.mp3_build import _mp3_asset_dest_for_flac_path
    from tagslut.utils.env_paths import get_volume

    flac_paths = _read_stage_paths(result, stage_name="mp3")
    if not flac_paths:
        return []
    library_root = get_volume("library", required=False)
    seen: set[str] = set()
    mp3_paths: list[Path] = []
    for flac_path in flac_paths:
        dest = _mp3_asset_dest_for_flac_path(
            flac_path=flac_path,
            mp3_root=mp3_root,
            library_root=library_root,
        ).resolve()
        if not dest.exists():
            continue
        key = str(dest)
        if key in seen:
            continue
        seen.add(key)
        mp3_paths.append(dest)
    return mp3_paths


def _write_url_mp3_playlists(
    *,
    result: IntakeResult,
    mp3_root: Path,
    dj: bool,
    run_started: float,
) -> list[Path]:
    mp3_paths = _resolve_url_mp3_paths(result=result, mp3_root=mp3_root)
    if not mp3_paths:
        return []

    playlist_name = _latest_run_playlist_name(run_started=run_started) or _fallback_mp3_playlist_name(
        mp3_paths=mp3_paths,
        mp3_root=mp3_root,
    )

    if dj:
        batch_path, global_path = write_dj_pool_m3u(
            mp3_paths=mp3_paths,
            mp3_root=mp3_root,
            playlist_name=playlist_name,
        )
        return [batch_path.resolve(), global_path.resolve()]

    batch_dir = _common_parent_dir(mp3_paths)
    batch_path = write_m3u(
        playlist_name=playlist_name or "playlist",
        files=mp3_paths,
        output_dir=batch_dir,
        path_mode="absolute",
    )
    return [batch_path.resolve()]


def _run_url_flow(
    *,
    url: str,
    db_path: Path,
    cohort_id: int,
    dj: bool,
    mp3: bool,
    playlist: bool,
    existing_batch_root: Path | None = None,
    raw_backend: bool = False,
) -> tuple[bool, str | None]:
    mp3_requested = bool(mp3 or dj)
    mp3_root = (
        Path(os.environ.get("MP3_LIBRARY") or _DEFAULT_MP3_LIBRARY).expanduser().resolve()
        if mp3_requested
        else None
    )
    playlist_paths: list[Path] = []
    run_started = time.time()
    artifact_dir = (get_artifacts_dir() / "intake").resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if existing_batch_root is not None and "qobuz.com" in url:
        result = _run_existing_qobuz_batch_flow(
            url=url,
            db_path=db_path,
            batch_root=existing_batch_root,
            run_started=run_started,
        )
    else:
        result = run_intake(
            url=url,
            db_path=db_path,
            tag=True,
            mp3=mp3_requested,
            dj=False,
            dry_run=False,
            mp3_root=mp3_root,
            artifact_dir=artifact_dir,
            verbose=True,
            debug_raw=raw_backend,
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
        if mp3_requested and mp3_root is not None:
            try:
                playlist_paths = _write_url_mp3_playlists(
                    result=result,
                    mp3_root=mp3_root,
                    dj=dj,
                    run_started=run_started,
                )
            except Exception as exc:
                record_blocked_paths(
                    conn,
                    cohort_id=cohort_id,
                    stage="playlist",
                    reason=str(exc),
                    paths=flac_paths,
                    placeholder_source=url,
                )
                conn.commit()
                click.echo(result.summary())
                click.echo(f"playlist: {exc}", err=True)
                return False, str(exc)

        refresh_cohort_status(conn, cohort_id=cohort_id)
        conn.commit()

    click.echo(result.summary())
    _echo_stage_details(result, playlist_paths=playlist_paths)
    return True, None


def register_get_command(cli: click.Group) -> None:
    @cli.command(
        "get",
        help=(
            "Download and ingest a provider URL or local path. "
            "Runs precheck → download → tag → promote → M3U. "
            "Add --mp3 to build tagged MP3 output, --dj for DJ playlists, "
            "--fix to resume a blocked cohort."
        ),
    )
    @click.argument("input_value")
    @click.option("--db", "db_path_arg", type=click.Path(), help="Database path (or TAGSLUT_DB)")
    @click.option("--dj", is_flag=True, help="Build MP3 output with DJ playlists.")
    @click.option("--mp3", is_flag=True, help="Build tagged MP3 output with a batch MP3 playlist.")
    @click.option("--playlist", is_flag=True, help="Emit M3U only; does not imply --dj.")
    @click.option(
        "--tag",
        "tag_local",
        is_flag=True,
        help="For a local directory, run staged intake (register -> enrich -> promote -> M3U) with source auto-detection.",
    )
    @click.option("--fix", "fix_mode", is_flag=True, help="Resume the most recent blocked cohort for this source.")
    def get_command(  # type: ignore[misc]
        input_value: str,
        db_path_arg: str | None,
        dj: bool,
        mp3: bool,
        playlist: bool,
        tag_local: bool,
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
                    flags=_cohort_flags(input_value=source_value, dj=dj, mp3=mp3, playlist=playlist),
                )
                conn.commit()

            ok, reason = _run_url_flow(
                url=source_value,
                db_path=db_path,
                cohort_id=cohort_id,
                dj=dj,
                mp3=mp3,
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
        if mp3:
            raise click.ClickException(
                "--mp3 is only supported for URL intake. Use `tagslut mp3` or `tagslut tag <path> --dj` for local paths."
            )
        if tag_local and dj:
            raise click.ClickException("--dj is not supported with local staged get. Use `tagslut tag <path> --dj` after intake.")
        if tag_local:
            ok, reason = _run_local_stage_flow(input_path=input_path, db_path=db_path)
            if not ok:
                click.echo(reason or "local staged get failed", err=True)
            raise SystemExit(0 if ok else 2)

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
                flags=_cohort_flags(input_value=str(input_path), dj=dj, mp3=mp3, playlist=playlist),
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
