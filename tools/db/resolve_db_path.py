#!/usr/bin/env python3
import sys
from pathlib import Path

import click

# Ensure imports work when running as a script
sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.utils.cli_helper import common_options, configure_execution
from dedupe.utils.config import get_config
from dedupe.utils.db import resolve_db_path


@click.command()
@click.option("--db", required=False, type=click.Path(dir_okay=False), help="Optional DB path override")
@click.option("--allow-repo-db", is_flag=True, default=False, help="Allow repo-local DB paths")
@click.option("--create-db", is_flag=True, default=False, help="Allow creation of a new DB file")
@click.option(
    "--purpose",
    type=click.Choice(["read", "write"], case_sensitive=False),
    default="write",
    show_default=True,
    help="Resolve for read or write behavior (write enforces repo guard)",
)
@click.option("--print-path", is_flag=True, default=False, help="Print only the resolved path")
@common_options
def main(
    db: str | None,
    allow_repo_db: bool,
    create_db: bool,
    purpose: str,
    print_path: bool,
    verbose: bool,
    config: str | None,
) -> None:
    """Print the resolved DB path and precedence chain."""
    configure_execution(verbose, config)
    app_config = get_config()
    repo_root = Path(__file__).parents[2].resolve()

    try:
        resolution = resolve_db_path(
            db,
            config=app_config,
            allow_repo_db=allow_repo_db,
            repo_root=repo_root,
            purpose=purpose,
            allow_create=create_db,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc))

    if print_path:
        click.echo(str(resolution.path))
        return

    click.echo("Resolved DB Path")
    click.echo(f"  Path: {resolution.path}")
    click.echo(f"  Source: {resolution.source}")
    click.echo(f"  Exists: {'yes' if resolution.exists else 'no'}")
    click.echo(f"  Purpose: {resolution.purpose}")
    click.echo("Precedence")
    click.echo("  cli (--db) > env (DEDUPE_DB) > config (db.path)")
    click.echo("Candidates")
    for source, value in resolution.candidates:
        label = value if value else "(not set)"
        click.echo(f"  {source}: {label}")


if __name__ == "__main__":
    main()
