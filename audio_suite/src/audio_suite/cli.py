"""Command‑line entry point for Audio Suite.

This module wires together the various subcomponents of the package into a
cohesive Typer application.  Each command delegates its work to a
corresponding function in the :mod:`audio_suite.core`, :mod:`audio_suite.plugins`
or :mod:`audio_suite.get` namespaces.  Commands are intentionally shallow
wrappers to keep the CLI responsive and maintainable.
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Optional, List

import typer
from rich.console import Console

from .core import config as core_config
from .core import db as core_db
from .core import utils as core_utils
from .plugins.match import engine as match_engine
from .plugins.export import playlist as export_playlist
from .get.providers import qobuz, tidal
from .tui import wizard as tui_wizard


app = typer.Typer(name="audio-suite", help="Manage FLAC libraries, match playlists and download tracks.")


@app.command("init")
def init_config() -> None:
    """Run the interactive setup wizard to configure your environment.

    This command launches a full‑screen wizard that will guide you through
    selecting music library roots, choosing a database location and setting
    output paths.  Existing configuration values are loaded and displayed
    as defaults.
    """
    tui_wizard.run_wizard()


@app.command("scan")
def scan_library(force: bool = typer.Option(False, help="Rescan all tracks even if unchanged")) -> None:
    """Scan your music library and populate the database.

    This command looks at the configured `library_roots` and updates the
    SQLite database with metadata for all FLAC files it finds.  If the
    database does not exist it will be created automatically.
    """
    settings = core_config.get_settings()
    db = core_db.get_engine(settings)
    console = Console()
    console.print("Scanning library…")
    core_db.initialise_database(db)
    core_db.scan_music(db, settings.library_roots.split(","), force=force)
    console.print("Scan complete.")


@app.command("match")
def match_playlist(
    playlist_path: pathlib.Path = typer.Argument(..., exists=True, readable=True, help="Path to input playlist (M3U, JSON or TXT)."),
    review: bool = typer.Option(False, help="Force manual review even for high‑confidence matches."),
    output: Optional[pathlib.Path] = typer.Option(None, help="Optional path to write a JSON report of all matches."),
) -> None:
    """Match a playlist against your local library.

    The input playlist can be in M3U/M3U8, JSON or plain‑text format.  Audio
    Suite will parse the file, perform fuzzy matching against the track
    database and either accept matches automatically or prompt you for
    confirmation depending on the configured thresholds and the `--review`
    flag.  The resulting match report can be written to a JSON file for
    further processing.
    """
    settings = core_config.get_settings()
    engine = core_db.get_engine(settings)
    core_db.initialise_database(engine)
    results = match_engine.match_playlist(str(playlist_path), engine, settings, review=review)
    if output is not None:
        output.write_text(json.dumps(results, indent=2), encoding="utf-8")
        typer.echo(f"Wrote match report to {output}")


@app.command("export")
def export_results(
    playlist_path: pathlib.Path = typer.Argument(..., exists=True, readable=True, help="Input playlist used for matching."),
    format: str = typer.Argument(..., help="Export format: m3u | json | songshift"),
    output: Optional[pathlib.Path] = typer.Option(None, help="Override output path.")
) -> None:
    """Export previously matched results in various formats.

    After running `audio-suite match` you can use this command to generate
    files compatible with media players (M3U), analysis tools (JSON) or
    SongShift.  If no output path is provided, the configured default
    location is used.
    """
    settings = core_config.get_settings()
    path = export_playlist.export(playlist_path=str(playlist_path), fmt=format, settings=settings, output=output)
    typer.echo(f"Exported to {path}")


@app.command("get")
def get_track(
    provider: str = typer.Argument(..., help="Streaming provider to fetch from (e.g. 'qobuz' or 'tidal')."),
    identifier: str = typer.Argument(..., help="Track URL or identifier."),
    output: Optional[pathlib.Path] = typer.Option(None, help="Destination directory or file name for the downloaded FLAC."),
) -> None:
    """Download a FLAC file from a streaming provider.

    This command delegates to the appropriate provider module based on the
    first argument.  Credentials and API keys are looked up via the
    keyring and environment variables.  Downloads are saved to the
    configured output directory unless overridden.
    """
    settings = core_config.get_settings()
    if provider == "qobuz":
        path = qobuz.download_track(identifier, settings, output)
    elif provider == "tidal":
        path = tidal.download_track(identifier, settings, output)
    else:
        typer.echo(f"Unsupported provider: {provider}")
        raise typer.Exit(code=1)
    typer.echo(f"Downloaded track to {path}")


@app.command("config")
def show_config() -> None:
    """Display the current effective configuration."""
    settings = core_config.get_settings()
    console = Console()
    console.print("Configuration:")
    console.print(json.dumps(settings.as_dict(), indent=2))


def app_main(argv: Optional[List[str]] = None) -> int:
    """Entry point for packaging systems.

    Allows the CLI to be invoked programmatically with a list of arguments.  If
    called with no arguments, it uses `sys.argv[1:]`.
    """
    return typer.run(app, argv or sys.argv[1:])


if __name__ == "__main__":
    app_main()