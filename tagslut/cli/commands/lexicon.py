"""CLI commands for Lexicon DJ library import and reconciliation."""
from __future__ import annotations

import click


@click.group("lexicon", help="Import and reconcile Lexicon DJ library data.")
def lexicon_group() -> None:
    pass


@lexicon_group.command("import", help="Import Lexicon track metadata into TAGSLUT_DB.")
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option(
    "--lexicon",
    "lexicon_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to lexicondj.db (Lexicon SQLite database).",
)
@click.option("--run-id", "run_id", default="", help="Session run ID (generated if empty).")
@click.option("--log-dir", "log_dir", default="data/logs", help="Directory for JSONL logs.")
@click.option(
    "--prefer-lexicon",
    is_flag=True,
    default=False,
    help="Overwrite non-null fields with Lexicon values.",
)
@click.option(
    "--dry-run/--execute",
    default=True,
    show_default=True,
    help="Dry-run counts without writing to DB.",
)
def lexicon_import(
    db_path: str | None,
    lexicon_path: str,
    run_id: str,
    log_dir: str,
    prefer_lexicon: bool,
    dry_run: bool,
) -> None:
    """Import Lexicon DJ library metadata into TAGSLUT_DB."""
    import sqlite3
    from pathlib import Path

    from tagslut.exec.lexicon_import import import_lexicon_metadata
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    _run_id = run_id or "a655f8d4-c88b-4986-8a92-8e952848a75d"

    conn = sqlite3.connect(str(resolved_db))
    try:
        result = import_lexicon_metadata(
            conn,
            lexicon_db_path=Path(lexicon_path),
            run_id=_run_id,
            log_dir=Path(log_dir),
            prefer_lexicon=prefer_lexicon,
            dry_run=dry_run,
        )
    finally:
        conn.close()

    matched = result.get("matched", 0)
    written = result.get("fields_written", 0)
    skipped = result.get("skipped_non_null", 0)
    errors = result.get("errors", 0)
    click.echo(
        f"[TASK 4 COMPLETE] {matched} tracks matched, {written} fields written, "
        f"{skipped} skipped, {errors} errors"
    )
    if dry_run:
        click.secho("Dry-run complete. Pass --execute to commit.", fg="yellow")


@lexicon_group.command("import-playlists", help="Import Lexicon playlists into TAGSLUT_DB.")
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option(
    "--lexicon",
    "lexicon_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to lexicondj.db (Lexicon SQLite database).",
)
@click.option("--run-id", "run_id", default="", help="Session run ID.")
@click.option("--log-dir", "log_dir", default="data/logs", help="Directory for JSONL logs.")
@click.option(
    "--dry-run/--execute",
    default=True,
    show_default=True,
    help="Dry-run counts without writing to DB.",
)
def lexicon_import_playlists(
    db_path: str | None,
    lexicon_path: str,
    run_id: str,
    log_dir: str,
    dry_run: bool,
) -> None:
    """Import selected Lexicon playlists into dj_playlist and dj_playlist_track."""
    import sqlite3
    from pathlib import Path

    from tagslut.exec.lexicon_import import import_lexicon_playlists
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    _run_id = run_id or "a655f8d4-c88b-4986-8a92-8e952848a75d"

    conn = sqlite3.connect(str(resolved_db))
    try:
        result = import_lexicon_playlists(
            conn,
            lexicon_db_path=Path(lexicon_path),
            run_id=_run_id,
            log_dir=Path(log_dir),
            dry_run=dry_run,
        )
    finally:
        conn.close()

    playlists = result.get("playlists_imported", 0)
    tracks = result.get("tracks_linked", 0)
    skipped = result.get("skipped", 0)
    click.echo(
        f"[TASK 5 COMPLETE] {playlists} playlists imported, {tracks} tracks linked, {skipped} skipped"
    )
    if dry_run:
        click.secho("Dry-run complete. Pass --execute to commit.", fg="yellow")
