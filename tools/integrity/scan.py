import sys
import click
from pathlib import Path

# Ensure we can import dedupe from root
sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.integrity_scanner import scan_library
from dedupe.utils.cli_helper import common_options, configure_execution

@click.command()
@click.argument("library_path", type=click.Path(exists=True, file_okay=False))
@click.option("--db", required=True, type=click.Path(dir_okay=False), help="Path to SQLite database")
@click.option("--library", default=None, help="Logical library name (e.g. COMMUNE)")
@click.option(
    "--zone",
    type=click.Choice(["staging", "accepted"]),
    default=None,
    help="COMMUNE zone to tag (staging or accepted)",
)
@click.option(
    "--incremental/--no-incremental",
    default=False,
    help="Skip unchanged files by comparing mtime/size stored in the DB",
)
@click.option(
    "--recheck/--no-recheck",
    default=False,
    help="Force re-scan of all files even if unchanged (overrides --incremental)",
)
@click.option(
    "--progress/--no-progress",
    default=False,
    help="Log periodic progress while processing files",
)
@click.option(
    "--progress-interval",
    type=int,
    default=250,
    show_default=True,
    help="When --progress is enabled, log every N processed files",
)
@click.option("--check-integrity/--no-check-integrity", default=False, help="Run flac -t verification")
@click.option("--check-hash/--no-check-hash", default=True, help="Calculate SHA256 checksums")
@common_options
def scan(library_path, db, library, zone, incremental, recheck, progress, progress_interval, check_integrity, check_hash, verbose, config):
    """
    Scans a library folder for FLAC files and populates the database.
    """
    configure_execution(verbose, config)
    
    lib_path = Path(library_path)
    db_path = Path(db)
    
    click.echo(f"Scanning Library: {lib_path}")
    click.echo(f"Database: {db_path}")
    if library:
        click.echo(f"Library Tag: {library}")
    if zone:
        click.echo(f"Zone: {zone}")
    click.echo(f"Incremental: {'ON' if incremental else 'OFF'}")
    click.echo(f"Recheck: {'ON' if recheck else 'OFF'}")
    click.echo(f"Progress: {'ON' if progress else 'OFF'}")
    if progress:
        click.echo(f"Progress Interval: {progress_interval}")
    click.echo(f"Integrity Check: {'ON' if check_integrity else 'OFF'}")
    click.echo(f"Hash Calculation: {'ON' if check_hash else 'OFF'}")
    
    try:
        scan_library(
            library_path=lib_path,
            db_path=db_path,
            library=library,
            zone=zone,
            incremental=incremental,
            recheck=recheck,
            progress=progress,
            progress_interval=progress_interval,
            scan_integrity=check_integrity,
            scan_hash=check_hash
        )
        click.echo(click.style("Scan complete.", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Scan failed: {e}", fg="red"), err=True)
        sys.exit(1)

if __name__ == "__main__":
    scan()
