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
    type=click.Path(exists=True, path_type=Path),  # type: ignore  # TODO: mypy-strict
    help="USB mount point",
)
@click.option(
    "--dj-pool",
    type=click.Path(path_type=Path),  # type: ignore  # TODO: mypy-strict
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
@click.option("--usb", required=True, type=click.Path(exists=True, path_type=Path))  # type: ignore  # TODO: mypy-strict
@click.option("--db", "db_path", required=True, type=click.Path())
@click.option("--verbose", is_flag=True, help="Show per-file diff details")
def gig_status(usb: Path, db_path: str, verbose: bool) -> None:
    """Show what's on the USB and flag stale tracks vs current inventory."""
    from tagslut.exec.usb_export import scan_source
    from tagslut.storage.schema import get_connection

    with get_connection(db_path, purpose="read") as conn:
        gig_set = conn.execute(
            """
            SELECT id, name
            FROM gig_sets
            WHERE usb_path = ?
            ORDER BY COALESCE(exported_at, created_at) DESC, id DESC
            LIMIT 1
            """,
            (str(usb),),
        ).fetchone()
        if gig_set is None:
            gig_set = conn.execute(
                """
                SELECT id, name
                FROM gig_sets
                ORDER BY COALESCE(exported_at, created_at) DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        if gig_set is None:
            raise click.ClickException("No gig sets found in DB.")

        rows = conn.execute(
            """
            SELECT file_path, mp3_path, usb_dest_path
            FROM gig_set_tracks
            WHERE gig_set_id = ?
            """,
            (int(gig_set["id"]),),
        ).fetchall()

    expected_names: set[str] = set()
    expected_by_name: dict[str, str] = {}
    for row in rows:
        candidates = [row["usb_dest_path"], row["mp3_path"], row["file_path"]]
        chosen = next((str(value) for value in candidates if value), None)
        if not chosen:
            continue
        name = Path(chosen).name
        key = name.lower()
        expected_names.add(key)
        expected_by_name[key] = name

    usb_tracks = scan_source(usb / "MUSIC") if (usb / "MUSIC").exists() else []
    usb_by_name = {track.name.lower(): track.name for track in usb_tracks}
    actual_names = set(usb_by_name.keys())

    current = sorted(expected_names & actual_names)
    missing = sorted(expected_names - actual_names)
    stale = sorted(actual_names - expected_names)

    click.echo(f"USB: {usb}")
    click.echo(f"Gig set: {gig_set['name']} (id={gig_set['id']})")
    click.echo(f"Expected tracks: {len(expected_names)}")
    click.echo(f"Tracks on USB:   {len(actual_names)}")
    click.echo(f"Current:         {len(current)}")
    click.echo(f"Stale:           {len(stale)}")
    click.echo(f"Missing:         {len(missing)}")

    if verbose:
        if current:
            click.echo("\nCurrent tracks:")
            for key in current:
                click.echo(f"  {expected_by_name.get(key, key)}")
        if stale:
            click.echo("\nStale tracks:")
            for key in stale:
                click.echo(f"  {usb_by_name.get(key, key)}")
        if missing:
            click.echo("\nMissing tracks:")
            for key in missing:
                click.echo(f"  {expected_by_name.get(key, key)}")

    if missing:
        raise click.exceptions.Exit(1)


@gig_group.command("apply-rekordbox-overlay")
@click.option(
    "--input-xml",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Input Rekordbox XML export",
)
@click.option(
    "--output-xml",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output Rekordbox XML with track-level overlay fields applied",
)
@click.option(
    "--overlay-config",
    default=Path("config/gig_overlay_rules.yaml"),
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="YAML overlay rules file",
)
@click.option(
    "--audit-csv",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional audit CSV path. Defaults to <output>.overlay_audit.csv",
)
@click.option(
    "--audit-json",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Optional audit JSON path",
)
@click.option("--no-backup", is_flag=True, help="Do not back up an existing output XML")
@click.option("--dry-run", is_flag=True, help="Compute overlay decisions without writing XML")
def apply_rekordbox_overlay_command(
    input_xml: Path,
    output_xml: Path,
    overlay_config: Path,
    audit_csv: Path | None,
    audit_json: Path | None,
    no_backup: bool,
    dry_run: bool,
) -> None:
    """Apply gig-use Rating and Colour overlays to a Rekordbox XML export."""
    from tagslut.adapters.rekordbox.overlay import apply_rekordbox_overlay

    resolved_audit_csv = audit_csv
    if resolved_audit_csv is None:
        resolved_audit_csv = output_xml.with_suffix(".overlay_audit.csv")

    result = apply_rekordbox_overlay(
        input_xml=input_xml,
        output_xml=output_xml,
        config_path=overlay_config,
        audit_csv_path=resolved_audit_csv,
        audit_json_path=audit_json,
        backup_existing=not no_backup,
        dry_run=dry_run,
    )

    click.echo(f"Tracks scanned:            {result.tracks_scanned}")
    click.echo(f"Tracks changed:           {result.tracks_changed}")
    click.echo(f"Rating changes:           {result.rating_changed}")
    click.echo(f"Colour changes:           {result.colour_changed}")
    click.echo(f"Manual overrides applied: {result.manual_overrides_applied}")
    click.echo(f"Preserved existing:       {result.preserved_existing}")
    if dry_run:
        click.echo(f"Dry run output target:    {output_xml}")
    else:
        click.echo(f"Output XML:               {output_xml}")
        if result.backup_path:
            click.echo(f"Backup XML:               {result.backup_path}")
    if result.audit_csv_path:
        click.echo(f"Audit CSV:                {result.audit_csv_path}")
    if result.audit_json_path:
        click.echo(f"Audit JSON:               {result.audit_json_path}")
