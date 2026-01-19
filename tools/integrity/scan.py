import sys
import click
from pathlib import Path
from typing import Any

# Ensure we can import dedupe from root
sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.integrity_scanner import scan_library
from dedupe.utils import env_paths
from dedupe.utils.cli_helper import common_options, configure_execution
from dedupe.utils.config import get_config
from dedupe.utils.db import resolve_db_path

@click.command()
@click.argument("library_path", type=click.Path(exists=True, file_okay=False), required=False)
@click.option("--db", required=False, type=click.Path(dir_okay=False), help="Path to SQLite database (default: $DEDUPE_DB)")
@click.option("--create-db", is_flag=True, default=False, help="Allow creating a new DB file")
@click.option("--paths-from-file", type=click.Path(exists=True, dir_okay=False), help="Read specific file paths from this file (one per line)")
@click.option("--library", default=None, help="Logical library name (e.g. COMMUNE)")
@click.option(
    "--incremental/--no-incremental",
    default=True,
    help="Skip unchanged files unless checks are missing or stale (default: incremental)",
)
@click.option(
    "--recheck/--no-recheck",
    default=False,
    help="Re-run requested checks for missing/stale/failed files (does not force full rescan)",
)
@click.option(
    "--force-all",
    is_flag=True,
    default=False,
    help="Force all requested checks on all files regardless of prior results",
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
@click.option("--allow-repo-db", is_flag=True, default=False, help="Allow writing to a repo-local DB path")
@click.option("--stale-days", type=int, default=None, help="Treat integrity/hash results older than N days as stale")
@click.option("--error-log", type=click.Path(dir_okay=False), default=None, help="Path to append scan error details (default: scan_errors.log in cwd)")
@common_options
def scan(
    library_path: str | None,
    db: str | None,
    create_db: bool,
    paths_from_file: str | None,
    library: str | None,
    incremental: bool,
    recheck: bool,
    force_all: bool,
    progress: bool,
    progress_interval: int,
    limit: int | None,
    check_integrity: bool,
    check_hash: bool,
    hard_skip: bool,
    allow_repo_db: bool,
    stale_days: int | None,
    error_log: str | None,
    verbose: bool,
    config: str | None,
) -> None:
    """
    Scans a library folder for FLAC files and populates the database.

    Zones are now auto-assigned based on scan results and file location.

    If --paths-from-file is provided, ignores LIBRARY_PATH and scans only specified files.
    """
    app_config = get_config(Path(config) if config else None)
    ctx = click.get_current_context()

    def _apply_default(
        param_name: str,
        current_value: Any,
        config_key: str,
        fallback: Any = None,
    ) -> Any:
        if ctx.get_parameter_source(param_name) == click.core.ParameterSource.DEFAULT:
            value = app_config.get(config_key, fallback)
            if value is not None:
                return value
        return current_value

    verbose = _apply_default("verbose", verbose, "integrity.verbose", app_config.get("scan.verbose", False))
    progress = _apply_default("progress", progress, "integrity.progress", False)
    progress_interval = _apply_default("progress_interval", progress_interval, "integrity.progress_interval", progress_interval)
    incremental = _apply_default("incremental", incremental, "integrity.incremental", incremental)
    recheck = _apply_default("recheck", recheck, "integrity.recheck", recheck)
    force_all = _apply_default("force_all", force_all, "integrity.force_all", force_all)
    check_integrity = _apply_default("check_integrity", check_integrity, "integrity.check_integrity", check_integrity)
    check_hash = _apply_default("check_hash", check_hash, "integrity.check_hash", check_hash)
    hard_skip = _apply_default("hard_skip", hard_skip, "integrity.hard_skip", hard_skip)
    stale_days = _apply_default("stale_days", stale_days, "integrity.stale_days", stale_days)
    allow_repo_db = _apply_default("allow_repo_db", allow_repo_db, "integrity.allow_repo_db", allow_repo_db)
    create_db = _apply_default("create_db", create_db, "integrity.create_db", create_db)

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
    try:
        resolution = resolve_db_path(
            db,
            config=app_config,
            allow_repo_db=allow_repo_db,
            repo_root=repo_root,
            purpose="write",
            allow_create=create_db,
        )
    except ValueError as e:
        raise click.ClickException(str(e))
    db_path = resolution.path
    db_source = resolution.source

    # Load specific paths if provided
    specific_paths = None
    if paths_from_file:
        paths_file = Path(paths_from_file).expanduser().resolve()
        click.echo(f"Loading paths from: {paths_file}")
        with open(paths_file) as f:
            specific_paths = [Path(line.strip()).expanduser().resolve() for line in f if line.strip()]
        click.echo(f"Loaded {len(specific_paths)} paths to scan")
        lib_path = None
        paths_from_file_path = paths_file
    else:
        assert library_path is not None
        lib_path = Path(library_path).expanduser().resolve()
        paths_from_file_path = None

    if lib_path:
        click.echo(f"Scanning Library: {lib_path}")
    else:
        click.echo(f"Scanning {len(specific_paths or [])} specific paths")
    click.echo(f"Database: {db_path} (source={db_source})")
    if library:
        click.echo(f"Library Tag: {library}")
    click.echo(f"Zone: auto-assigned based on scan results")
    click.echo(f"Incremental: {'ON' if incremental else 'OFF'}")
    click.echo(f"Recheck: {'ON' if recheck else 'OFF'}")
    click.echo(f"Force All: {'ON' if force_all else 'OFF'}")
    click.echo(f"Progress: {'ON' if progress else 'OFF'}")
    if progress:
        click.echo(f"Progress Interval: {progress_interval}")
    if limit:
        click.echo(f"Batch Limit: {limit} files")
    click.echo(f"Integrity Check: {'ON' if check_integrity else 'OFF'}")
    click.echo(f"Hash Calculation: {'ON' if check_hash else 'OFF'}")
    if stale_days is not None:
        click.echo(f"Stale Days: {stale_days}")
    if error_log:
        click.echo(f"Error log: {error_log}")
    else:
        click.echo(f"Error log: {env_paths.get_reports_dir() / 'scan_errors.log'} (default)")

    error_log_path = Path(error_log) if error_log else env_paths.get_log_path("scan_errors.log")
    error_log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        outcome = scan_library(
        library_path=lib_path,
        db_path=db_path,
        db_source=db_source,
        library=library,
        recheck=recheck,
        force_all=force_all,
        progress=progress,
        progress_interval=progress_interval,
        scan_integrity=check_integrity,
        scan_hash=check_hash,
        specific_paths=specific_paths,
        limit=limit,
        stale_days=stale_days,
        paths_source="paths-from-file" if paths_from_file else None,
        paths_from_file=paths_from_file_path,
        create_db=create_db,
        allow_repo_db=allow_repo_db,
        error_log=error_log_path,
    )
        if outcome.status == "completed":
            click.echo(click.style("Scan complete.", fg="green"))
        elif outcome.status == "aborted":
            click.echo(click.style("Scan aborted.", fg="yellow"))
        else:
            click.echo(click.style("Scan failed.", fg="red"))
            sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"Scan failed: {e}", fg="red"), err=True)
        sys.exit(1)

if __name__ == "__main__":
    scan()
