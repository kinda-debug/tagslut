import click
import logging
import sys
from pathlib import Path

# Add project root to path so we can import tools as modules if needed
sys.path.insert(0, str(Path(__file__).parents[2]))

logger = logging.getLogger("dedupe")


@click.group()
@click.version_option(version="2.0.0")
def cli():
    """Dedupe Library Management CLI"""
    pass


@cli.command(context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def scan(args):
    """Scan a library volume (legacy wrapper)"""
    from tools.integrity.scan import scan as scan_cmd
    # If -h or --help is in args, we want to let the underlying command handle it
    # but Click might intercept it before we get here.
    # That's why we use help_option_names=[]
    sys.argv = ['dedupe scan'] + list(args)
    scan_cmd()


@cli.command(context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def recommend(args):
    """Generate deduplication recommendations (legacy wrapper)"""
    from tools.decide.recommend import recommend as recommend_cmd
    sys.argv = ['dedupe recommend'] + list(args)
    recommend_cmd()


@cli.command(context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def apply(args):
    """Execute deduplication plan (legacy wrapper)"""
    from tools.decide.apply import apply as apply_cmd
    sys.argv = ['dedupe apply'] + list(args)
    apply_cmd()


def _interactive_init() -> dict:
    """
    Interactive session initialization.

    Prompts user for all required directories and settings.
    Returns a dict with configuration values.
    """
    click.echo("\n" + "=" * 60)
    click.echo("FLAC RECOVERY SESSION INITIALIZATION")
    click.echo("=" * 60)
    click.echo("\nThis wizard will help you set up a new recovery session.\n")

    config = {}

    # Source directory
    click.echo("1. SOURCE DIRECTORY")
    click.echo("   The directory containing FLAC files to scan and recover.")
    while True:
        source = click.prompt("   Enter source directory path", type=str)
        source_path = Path(source).expanduser().resolve()
        if source_path.is_dir():
            config["source"] = source_path
            click.echo(f"   -> {source_path}")
            break
        click.echo(f"   ERROR: '{source}' is not a valid directory. Try again.")

    # Database path
    click.echo("\n2. DATABASE")
    click.echo("   SQLite database to store scan results and recovery state.")
    default_db = Path.cwd() / "recovery.db"
    db = click.prompt("   Enter database path", default=str(default_db), type=str)
    config["db"] = Path(db).expanduser().resolve()
    click.echo(f"   -> {config['db']}")

    # Backup directory
    click.echo("\n3. BACKUP DIRECTORY")
    click.echo("   Where to store original files before repair (for safety).")
    click.echo("   Leave empty to skip backups (not recommended).")
    backup = click.prompt("   Enter backup directory path", default="", type=str)
    if backup:
        backup_path = Path(backup).expanduser().resolve()
        backup_path.mkdir(parents=True, exist_ok=True)
        config["backup_dir"] = backup_path
        click.echo(f"   -> {backup_path}")
    else:
        config["backup_dir"] = None
        click.echo("   -> (no backups)")

    # Output report
    click.echo("\n4. OUTPUT REPORT")
    click.echo("   Where to save the final recovery report.")
    default_output = Path.cwd() / "recovery_report.csv"
    output = click.prompt("   Enter report output path", default=str(default_output), type=str)
    config["output"] = Path(output).expanduser().resolve()
    click.echo(f"   -> {config['output']}")

    # Move mode
    click.echo("\n5. OPERATION MODE")
    click.echo("   Copy mode: Keep backups after successful recovery (safer)")
    click.echo("   Move mode: Delete backups after verification (saves space)")
    move = click.confirm("   Use move mode (delete backups after verification)?", default=False)
    config["move"] = move
    mode_msg = "Move mode (backups will be deleted)" if move else "Copy mode (backups preserved)"
    click.echo(f"   -> {mode_msg}")

    # Workers
    click.echo("\n6. PARALLEL WORKERS")
    workers = click.prompt("   Number of parallel scan workers", default=4, type=int)
    config["workers"] = workers
    click.echo(f"   -> {workers} workers")

    # Confirmation
    click.echo("\n" + "=" * 60)
    click.echo("CONFIGURATION SUMMARY")
    click.echo("=" * 60)
    click.echo(f"  Source:     {config['source']}")
    click.echo(f"  Database:   {config['db']}")
    click.echo(f"  Backup dir: {config['backup_dir'] or '(none)'}")
    click.echo(f"  Output:     {config['output']}")
    click.echo(f"  Mode:       {'Move' if config['move'] else 'Copy'}")
    click.echo(f"  Workers:    {config['workers']}")
    click.echo("=" * 60)

    if not click.confirm("\nProceed with these settings?", default=True):
        raise click.Abort()

    return config


@cli.command()
@click.argument('path', required=False, type=click.Path(exists=True))
@click.option('--db', type=click.Path(), help='Recovery database path')
@click.option(
    '--phase',
    type=click.Choice(['scan', 'repair', 'verify', 'report', 'all']),
    default='all',
    help='Pipeline phase to run (default: all)'
)
@click.option('--backup-dir', type=click.Path(), help='Directory for original file backups')
@click.option('--output', type=click.Path(), help='Report output path (CSV or JSON)')
@click.option('--workers', default=4, help='Parallel workers for scan phase')
@click.option('--execute', is_flag=True, help='Actually perform repairs (default: dry-run)')
@click.option('--move', is_flag=True, help='Delete backups after successful verification')
@click.option('--include-valid', is_flag=True, help='Include valid files in reports')
@click.option('--init', 'interactive', is_flag=True, help='Interactive session initialization')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def recover(
    path, db, phase, backup_dir, output, workers,
    execute, move, include_valid, interactive, verbose
):
    """
    Recover corrupted FLAC files.

    Scans for integrity issues, attempts FFmpeg-based salvage,
    verifies repairs, and generates reports.

    \b
    Examples:
        # Interactive session setup
        dedupe recover --init

        # Full pipeline (scan + repair + verify + report)
        dedupe recover /path/to/flacs --db recovery.db --execute

        # Scan only
        dedupe recover /path/to/flacs --db recovery.db --phase scan

        # Repair with backups (copy mode - keeps backups)
        dedupe recover --db recovery.db --phase repair --backup-dir /backups --execute

        # Repair with move mode (deletes backups after verification)
        dedupe recover --db recovery.db --phase repair --backup-dir /backups --execute --move

        # Generate report
        dedupe recover --db recovery.db --phase report --output report.csv
    """
    from dedupe.recovery import RecoveryScanner, Repairer, Verifier, Reporter
    from dedupe.storage.schema import init_db
    import sqlite3

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Interactive initialization
    if interactive:
        config = _interactive_init()
        path = str(config["source"])
        db = str(config["db"])
        backup_dir = str(config["backup_dir"]) if config["backup_dir"] else None
        output = str(config["output"])
        move = config["move"]
        workers = config["workers"]
        execute = True  # Interactive mode implies execution
        phase = 'all'

    # Validate required options
    if not db:
        raise click.ClickException("--db is required (or use --init for interactive setup)")

    db_path = Path(db)

    # Warn about move mode
    if move and execute:
        click.echo("\n" + "!" * 60)
        click.echo("WARNING: Move mode enabled!")
        click.echo("Backups will be DELETED after successful verification.")
        click.echo("This cannot be undone.")
        click.echo("!" * 60)
        if not click.confirm("Continue with move mode?", default=False):
            raise click.Abort()

    # Initialize database if needed
    if not db_path.exists():
        if phase in ('scan', 'all') and path:
            logger.info(f"Creating new database: {db_path}")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path)
            init_db(conn)
            conn.close()
        else:
            raise click.ClickException(f"Database not found: {db_path}")

    # Track repairer for potential backup cleanup
    repairer = None

    # Run requested phase(s)
    if phase in ('scan', 'all'):
        if not path:
            raise click.ClickException("PATH is required for scan phase")

        click.echo(f"\n{'='*50}")
        click.echo("PHASE 1: SCAN")
        click.echo(f"{'='*50}")

        scanner = RecoveryScanner(db_path, workers=workers)
        stats = scanner.scan_directory(Path(path))

        click.echo(f"Scanned: {stats['total']} files")
        click.echo(f"  Valid: {stats['valid']}")
        click.echo(f"  Corrupt: {stats['corrupt']}")
        click.echo(f"  Recoverable: {stats['recoverable']}")

    if phase in ('repair', 'all'):
        click.echo(f"\n{'='*50}")
        click.echo("PHASE 2: REPAIR")
        click.echo(f"{'='*50}")

        if not execute:
            click.echo("[DRY-RUN MODE - use --execute to perform repairs]")

        backup_path = Path(backup_dir) if backup_dir else None
        repairer = Repairer(
            db_path,
            backup_dir=backup_path,
            dry_run=not execute,
            move_mode=move,
        )
        stats = repairer.repair_all()

        click.echo(f"Processed: {stats['total']} files")
        click.echo(f"  Salvaged: {stats['salvaged']}")
        click.echo(f"  Already valid: {stats['already_valid']}")
        click.echo(f"  Failed: {stats['failed']}")
        if stats['skipped'] > 0:
            click.echo(f"  Skipped (dry-run): {stats['skipped']}")

    if phase in ('verify', 'all'):
        click.echo(f"\n{'='*50}")
        click.echo("PHASE 3: VERIFY")
        click.echo(f"{'='*50}")

        verifier = Verifier(db_path)
        stats = verifier.verify_all()

        click.echo(f"Verified: {stats['total']} files")
        click.echo(f"  Passed: {stats['passed']}")
        click.echo(f"  Degraded: {stats['degraded']}")
        click.echo(f"  Failed: {stats['failed']}")

        # Cleanup backups in move mode
        if move and execute and repairer:
            click.echo(f"\n{'='*50}")
            click.echo("CLEANUP: Deleting backups (move mode)")
            click.echo(f"{'='*50}")
            cleanup_stats = repairer.cleanup_backups(verified_only=True)
            click.echo(f"  Deleted: {cleanup_stats['deleted']}")
            click.echo(f"  Failed: {cleanup_stats['failed']}")
            click.echo(f"  Skipped: {cleanup_stats['skipped']}")

    if phase in ('report', 'all'):
        click.echo(f"\n{'='*50}")
        click.echo("PHASE 4: REPORT")
        click.echo(f"{'='*50}")

        reporter = Reporter(db_path)
        reporter.print_summary()

        if output:
            output_path = Path(output)
            if output_path.suffix.lower() == '.json':
                rows = reporter.export_json(output_path, include_valid=include_valid)
            else:
                rows = reporter.export_csv(output_path, include_valid=include_valid)
            click.echo(f"Exported {rows} records to {output_path}")


if __name__ == "__main__":
    cli()
