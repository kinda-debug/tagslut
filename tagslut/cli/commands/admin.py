from __future__ import annotations

import sqlite3

import click

from tagslut.cli.commands._cohort_state import ensure_cohort_support, list_blocked_cohorts
from tagslut.cli.commands.execute import register_execute_group
from tagslut.cli.commands.index import register_index_group
from tagslut.cli.commands.intake import register_intake_group
from tagslut.cli.commands.library import register_library_group
from tagslut.cli.commands.report import register_report_group
from tagslut.cli.commands.tag import register_curate_group
from tagslut.cli.commands.verify import register_verify_group
from tagslut.cli.commands.dj import dj_group
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path


def _source_summary(source_kind: str, source_url: str | None) -> str:
    if not source_url:
        return "(unknown source)"
    if source_kind == "local_path":
        parts = source_url.rstrip("/").split("/")
        return parts[-1] or source_url
    return source_url


def register_admin_group(cli: click.Group) -> None:
    @cli.group("admin")
    def admin():  # type: ignore[misc]
        """Internal and advanced workflow commands."""

    register_intake_group(admin)
    register_index_group(admin)
    register_execute_group(admin)
    register_verify_group(admin)
    register_report_group(admin)
    register_library_group(admin)
    admin.add_command(dj_group, name="dj")
    register_curate_group(admin)

    @admin.command("status")
    @click.option("--db", "db_path_arg", type=click.Path(), help="Database path (or TAGSLUT_DB)")
    def admin_status(db_path_arg: str | None) -> None:  # type: ignore[misc]
        try:
            resolution = resolve_cli_env_db_path(db_path_arg, purpose="read", source_label="--db")
        except DbResolutionError as exc:
            raise click.ClickException(str(exc)) from exc

        with sqlite3.connect(str(resolution.path)) as conn:
            ensure_cohort_support(conn)
            rows = list_blocked_cohorts(conn)

        if not rows:
            click.echo("No blocked cohorts.")
            return

        for row in rows:
            blocked_count = int(row[6] or 0)
            click.echo(
                f"{row[0]}  {_source_summary(str(row[2]), str(row[1]) if row[1] is not None else None)}  "
                f"status={row[3]}  blocked_files={blocked_count}  reason={row[4] or '(none)'}"
            )
