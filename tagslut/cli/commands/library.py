from __future__ import annotations

from pathlib import Path

import click

from tagslut.utils.config import get_config

_DEFAULT_LIBRARY_DB_URL = "sqlite:///~/.local/share/djtools/library.db"


def register_library_group(cli: click.Group) -> None:
    @cli.group()
    def library():  # type: ignore  # TODO: mypy-strict
        """Canonical library database workflows."""

    @library.command("import-rekordbox")
    @click.option(
        "--xml",
        "xml_path",
        required=True,
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help="Path to Rekordbox XML export",
    )
    @click.option(
        "--dry-run/--no-dry-run",
        default=True,
        help="Preview audit events only; do not commit track rows",
    )
    def import_rekordbox_command(xml_path: Path, dry_run: bool) -> None:  # type: ignore  # TODO: mypy-strict
        """Shadow-import Rekordbox XML into the library DB."""
        from tagslut.adapters.rekordbox.importer import import_rekordbox_xml

        db_url = str(get_config().get("library.db_url", _DEFAULT_LIBRARY_DB_URL))
        result = import_rekordbox_xml(xml_path, db_url, dry_run=dry_run)
        click.echo(f"Tracks seen: {result.tracks_seen}")
        click.echo(f"Tracks created: {result.tracks_created}")
        click.echo(f"Tracks updated: {result.tracks_updated}")
        if result.errors:
            for error in result.errors:
                click.echo(f"ERROR: {error}", err=True)
            raise click.ClickException("Rekordbox import finished with errors")
