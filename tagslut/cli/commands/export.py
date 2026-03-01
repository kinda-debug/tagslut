"""tagslut export -- USB and DJ pool export commands."""
from pathlib import Path

import click


@click.group("export")
def export_group() -> None:
    """Export tracks to USB or DJ pool."""


@export_group.command("usb")
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, path_type=Path),  # type: ignore  # TODO: mypy-strict
    help="Source directory containing audio files",
)
@click.option(
    "--usb",
    required=True,
    type=click.Path(exists=True, path_type=Path),  # type: ignore  # TODO: mypy-strict
    help="USB mount point (e.g. /Volumes/PIONEER_USB)",
)
@click.option(
    "--crate",
    default="tagslut export",
    show_default=True,
    help="Crate/playlist name in Rekordbox",
)
@click.option("--dry-run", is_flag=True, help="Print what would happen without writing anything")
def export_usb(source: Path, usb: Path, crate: str, dry_run: bool) -> None:
    """Export a folder of tracks to a Pioneer CDJ-ready USB."""
    from tagslut.exec.usb_export import copy_to_usb, scan_source, write_manifest, write_rekordbox_db

    tracks = scan_source(source)
    if not tracks:
        click.echo(f"No supported audio files found in {source}")
        raise SystemExit(1)

    click.echo(f"Found {len(tracks)} tracks in {source}")

    dest_tracks = copy_to_usb(tracks, usb, crate, dry_run=dry_run)
    write_rekordbox_db(dest_tracks, usb, crate, dry_run=dry_run)

    if not dry_run:
        manifest = write_manifest(dest_tracks, usb, crate)
        click.echo(f"Manifest: {manifest}")

    click.echo(f"{'[DRY RUN] ' if dry_run else ''}Export complete: {len(dest_tracks)} tracks → {usb}")
