"""tagslut gig -- DJ gig set management commands."""
from pathlib import Path

import click


@click.group("gig")
def gig_group() -> None:
    """Build and manage DJ gig sets."""


@gig_group.command("build")
@click.argument("name")
@click.option(
    "--filter",
    "filter_expr",
    default="dj_flag:true",
    show_default=True,
    help="Filter expression (e.g. 'genre:techno bpm:128-145 dj_flag:true')",
)
@click.option(
    "--usb",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="USB mount point",
)
@click.option(
    "--dj-pool",
    type=click.Path(path_type=Path),
    default=None,
    help="DJ pool directory for MP3s (default: from config)",
)
@click.option("--bitrate", default=320, show_default=True, help="MP3 bitrate in kbps")
@click.option("--db", "db_path", required=True, type=click.Path(), help="Path to tagslut DB")
@click.option("--dry-run", is_flag=True)
def gig_build(
    name: str,
    filter_expr: str,
    usb: Path,
    dj_pool: Path | None,
    bitrate: int,
    db_path: str,
    dry_run: bool,
) -> None:
    """Build a gig set and export to USB."""
    from tagslut.exec.gig_builder import GigBuilder
    from tagslut.storage.schema import get_connection
    from tagslut.utils.config import get_config

    if dj_pool is None:
        config = get_config()
        dj_pool = Path(config.get("dj_pool_dir", "~/Music/DJPool")).expanduser()

    click.echo(f"Building gig: {name!r}")
    click.echo(f"Filter: {filter_expr}")
    click.echo(f"USB: {usb}")
    if dry_run:
        click.echo("[DRY RUN] No files will be written.")

    with get_connection(db_path) as conn:
        builder = GigBuilder(conn, dj_pool_dir=dj_pool, mp3_bitrate=bitrate)
        result = builder.build(name, filter_expr, usb, dry_run=dry_run)

    click.echo(result.summary())
    if result.errors:
        click.echo(f"\n{len(result.errors)} errors:")
        for err in result.errors:
            click.echo(f"  - {err}")


@gig_group.command("list")
@click.option("--db", "db_path", required=True, type=click.Path())
def gig_list(db_path: str) -> None:
    """List all saved gig sets."""
    from tagslut.storage.schema import get_connection

    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT name, track_count, exported_at, usb_path FROM gig_sets ORDER BY exported_at DESC"
        ).fetchall()

    if not rows:
        click.echo("No gig sets found.")
        return

    for row in rows:
        click.echo(f"  {row[0]:<40} {row[1]:>4} tracks  {row[2] or 'never exported'}")


@gig_group.command("status")
@click.option("--usb", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--db", "db_path", required=True, type=click.Path())
def gig_status(usb: Path, db_path: str) -> None:
    """Show what's on the USB and flag stale tracks vs current inventory."""
    from tagslut.exec.usb_export import scan_source
    from tagslut.storage.schema import get_connection

    with get_connection(db_path, purpose="read"):
        pass

    usb_tracks = scan_source(usb / "MUSIC") if (usb / "MUSIC").exists() else []
    click.echo(f"USB: {usb}")
    click.echo(f"Tracks on USB: {len(usb_tracks)}")
    for track in usb_tracks:
        click.echo(f"  {track.name}")
