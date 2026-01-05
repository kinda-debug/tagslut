import sys
import click
from pathlib import Path

# Ensure we can import dedupe from root
sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.integrity_scanner import scan_library
from dedupe.utils.cli_helper import common_options, configure_execution

@click.command()
@click.argument("library_path", type=click.Path(exists=True, file_okay=False), required=False)
@click.option("--db", required=True, type=click.Path(dir_okay=False), help="Path to SQLite database")
@click.option("--paths-from-file", type=click.Path(exists=True, dir_okay=False), help="Read specific file paths from this file (one per line)")
@click.option("--library", default=None, help="Logical library name (e.g. COMMUNE)")
@click.option(
    "--zone",
    type=click.Choice(["staging", "accepted", "suspect", "quarantine"]),
    default=None,
    help="Zone to tag (staging, accepted, suspect, or quarantine)",
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
@click.option("--limit", type=int, default=None, help="Stop after processing N files (for batch processing)")
@click.option("--check-integrity/--no-check-integrity", default=False, help="Run flac -t verification")
@click.option("--check-hash/--no-check-hash", default=False, help="Calculate full-file SHA256 (Phase 3 only)")
@click.option("--hard-skip", is_flag=True, default=False, help="Alias for --no-check-integrity --no-check-hash (default behavior)")
@common_options
def scan(library_path, db, paths_from_file, library, zone, incremental, recheck, progress, progress_interval, limit, check_integrity, check_hash, hard_skip, verbose, config):
    """
    Scans a library folder for FLAC files and populates the database.
    
    If --paths-from-file is provided, ignores LIBRARY_PATH and scans only specified files.
    """
    configure_execution(verbose, config)
    
    # Validate arguments
    if not library_path and not paths_from_file:
        raise click.ClickException("Either LIBRARY_PATH or --paths-from-file must be provided")
    
    if library_path and paths_from_file:
        raise click.ClickException("Cannot use both LIBRARY_PATH and --paths-from-file")
    
    # Apply --hard-skip logic
    if hard_skip:
        check_integrity = False
        check_hash = False
    
    repo_root = Path(__file__).parents[2].resolve()
    db_path = Path(db).expanduser().resolve()
    
    # Load specific paths if provided
    specific_paths = None
    if paths_from_file:
        paths_file = Path(paths_from_file).expanduser().resolve()
        click.echo(f"Loading paths from: {paths_file}")
        with open(paths_file) as f:
            specific_paths = [Path(line.strip()).expanduser().resolve() for line in f if line.strip()]
        click.echo(f"Loaded {len(specific_paths)} paths to scan")
        lib_path = None
    else:
        lib_path = Path(library_path).expanduser().resolve()

    default_db = repo_root / "artifacts/db/music.db"
    if db_path == (repo_root / "music.db") and db_path.exists() and db_path.stat().st_size == 0:
        if default_db.exists():
            raise click.ClickException(
                f"{db_path} is empty (0 bytes). Did you accidentally delete it? "
                f"Use --db {default_db} (recommended) or remove the empty file."
            )
        raise click.ClickException(
            f"{db_path} is empty (0 bytes). Remove it or choose a different --db path."
        )
    
    if lib_path:
        click.echo(f"Scanning Library: {lib_path}")
    else:
        click.echo(f"Scanning {len(specific_paths)} specific paths")
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
    if limit:
        click.echo(f"Batch Limit: {limit} files")
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
            scan_hash=check_hash,
            specific_paths=specific_paths,
            limit=limit
        )
        click.echo(click.style("Scan complete.", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Scan failed: {e}", fg="red"), err=True)
        sys.exit(1)

if __name__ == "__main__":
    scan()
