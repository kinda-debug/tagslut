from __future__ import annotations

import sqlite3
from pathlib import Path

import click

from tagslut.cli.commands._cohort_state import (
    decode_flags,
    ensure_cohort_support,
    find_latest_blocked_cohort_for_source,
    get_cohort,
    list_blocked_cohorts,
    set_cohort_running,
)
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path


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
    set_cohort_running(conn, cohort_id=cohort_id)
    conn.commit()

    if source_kind == "url":
        ok, _reason = _run_url_flow(
            url=source_url,
            db_path=db_path,
            cohort_id=cohort_id,
            dj=bool(flags.get("dj")),
            playlist=bool(flags.get("playlist")),
        )
        return 0 if ok else 2

    input_path = Path(source_url).expanduser().resolve()
    ok, _reason = _run_local_flow(
        input_path=input_path,
        db_path=db_path,
        cohort_id=cohort_id,
        dj=bool(flags.get("dj")),
        playlist=bool(flags.get("playlist")),
    )
    return 0 if ok else 2


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
    @cli.command("fix")
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
