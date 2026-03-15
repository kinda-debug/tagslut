"""CLI commands for MP3 derivative management.

  tagslut mp3 build      — transcode preferred FLAC masters to MP3 and register in mp3_asset
  tagslut mp3 reconcile  — scan an existing MP3 root and link files to canonical identities
"""
from __future__ import annotations

import sys

import click


@click.group(
    "mp3",
    help="""
Build and reconcile MP3 derivative assets.

Part of the 4-stage DJ pipeline:
  Stage 1: build      → Transcode canonical FLAC masters to DJ MP3s
           reconcile  → Register existing DJ MP3s against canonical identities
  Stage 2: dj admit / dj backfill
  Stage 3: dj validate
  Stage 4: dj xml emit / dj xml patch

Common subcommands:
  build, reconcile

See: tagslut dj --help (Stages 2–4)
Docs: docs/DJ_WORKFLOW.md
""",
    epilog="""
Examples:
  # Reconcile existing MP3 directory
  tagslut mp3 reconcile --db <path> --mp3-root <path>

  # Build from FLAC masters
  tagslut mp3 build --db <path> --master-root <path> --dj-root <path>

Next: tagslut dj --help (Stages 2–4)
Then: tagslut dj backfill --db <path>
""",
)
def mp3_group() -> None:
    """Build and reconcile MP3 derivative assets."""


@mp3_group.command(
    "build",
    help="Build (transcode) MP3s from canonical FLAC masters. Stage 1a of DJ pipeline.",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option(
    "--dj-root",
    required=True,
    help="Output directory for transcoded MP3 files.",
    type=click.Path(file_okay=False, writable=True),
)
@click.option(
    "--identity-ids",
    default=None,
    help="Comma-separated identity IDs to build (default: all un-built identities).",
)
@click.option(
    "--dry-run/--execute",
    default=True,
    show_default=True,
    help="Dry-run counts what would be built without writing anything.",
)
def mp3_build(
    db_path: str | None,
    dj_root: str,
    identity_ids: str | None,
    dry_run: bool,
) -> None:
    """Transcode preferred FLAC masters to MP3 and register in mp3_asset.

    Only processes identities that do not already have an mp3_asset row
    with status='verified'. Safe to re-run (idempotent).
    """
    import sqlite3
    from pathlib import Path

    from tagslut.exec.mp3_build import build_mp3_from_identity
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    ids: list[int] | None = None
    if identity_ids:
        try:
            ids = [int(x.strip()) for x in identity_ids.split(",") if x.strip()]
        except ValueError as exc:
            raise click.ClickException(f"Invalid --identity-ids: {exc}") from exc

    conn = sqlite3.connect(str(resolved_db))
    try:
        result = build_mp3_from_identity(
            conn,
            identity_ids=ids,
            dj_root=Path(dj_root),
            dry_run=dry_run,
        )
    finally:
        conn.close()

    click.echo(result.summary())
    if result.errors:
        for err in result.errors:
            click.secho(f"  error: {err}", fg="red", err=True)

    if dry_run and result.built > 0:
        click.secho(
            f"Dry-run complete. Pass --execute to build {result.built} MP3(s).",
            fg="yellow",
        )

    sys.exit(1 if result.failed > 0 else 0)


@mp3_group.command(
    "reconcile",
    help="Reconcile existing MP3 directory with database. Stage 1 of the 4-stage DJ pipeline. Next step: tagslut dj backfill.",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option(
    "--mp3-root",
    required=True,
    help="Root directory of existing MP3 files to reconcile.",
    type=click.Path(exists=True, file_okay=False),
)
@click.option(
    "--dry-run/--execute",
    default=True,
    show_default=True,
    help="Dry-run counts what would be linked without writing anything.",
)
@click.option("--verbose", "-v", is_flag=True, default=False)
def mp3_reconcile(
    db_path: str | None,
    mp3_root: str,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Scan an existing MP3 root and link files to canonical identities in mp3_asset.

    Matches via ISRC tag first, then title+artist. Files that already have an
    mp3_asset row are skipped. Safe to re-run (idempotent).
    """
    import sqlite3
    from pathlib import Path

    from tagslut.exec.mp3_build import reconcile_mp3_library
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    conn = sqlite3.connect(str(resolved_db))
    try:
        result = reconcile_mp3_library(
            conn,
            mp3_root=Path(mp3_root),
            dry_run=dry_run,
        )
    finally:
        conn.close()

    click.echo(result.summary())
    if verbose and result.errors:
        for err in result.errors:
            click.echo(f"  {err}")
    elif result.errors:
        click.secho(
            f"  {len(result.errors)} file(s) had errors or no identity match "
            "(use --verbose to list them).",
            fg="yellow",
        )

    if dry_run and result.linked > 0:
        click.secho(
            f"Dry-run complete. Pass --execute to register {result.linked} MP3(s).",
            fg="yellow",
        )
