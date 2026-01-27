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
@click.option('--enrich', is_flag=True, help='Enrich salvaged files with metadata after verification')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def recover(
    path, db, phase, backup_dir, output, workers,
    execute, move, include_valid, interactive, enrich, verbose
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

    if enrich and phase in ('verify', 'all'):
        click.echo(f"\n{'='*50}")
        click.echo("PHASE 3.5: ENRICH SALVAGED FILES")
        click.echo(f"{'='*50}")

        from dedupe.metadata.enricher import Enricher
        from dedupe.metadata.auth import TokenManager

        token_manager = TokenManager()
        # Using default providers for now, could be an option
        provider_list = ["spotify", "beatport", "qobuz", "tidal", "itunes"]

        click.echo(f"Enriching with providers: {', '.join(provider_list)}")

        with Enricher(
            db_path=db_path,
            token_manager=token_manager,
            providers=provider_list,
            dry_run=not execute,
        ) as enricher:
            # Get salvaged and verified files
            path_pattern = """
                (SELECT path FROM files WHERE recovery_status = 'salvaged' AND verified_at IS NOT NULL)
            """
            # This is a bit of a hack; the enricher expects a LIKE pattern,
            # but we can use a subquery to get the exact paths.
            # A better solution would be a dedicated method in the enricher.
            
            # The enricher's get_eligible_files needs a LIKE pattern. 
            # This is a work-around and might be inefficient, but works for this scope.
            conn = sqlite3.connect(db_path)
            salvaged_paths = [row[0] for row in conn.execute("SELECT path FROM files WHERE recovery_status = 'salvaged' AND verified_at IS NOT NULL")]
            conn.close()

            if not salvaged_paths:
                click.echo("No salvaged and verified files to enrich.")
            else:
                for i, file_path in enumerate(salvaged_paths):
                    click.echo(f"Enriching [{i+1}/{len(salvaged_paths)}] {file_path}")
                    enricher.enrich_all(path_pattern=file_path, force=True)

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


@cli.group()
def metadata():
    """Metadata enrichment commands."""
    pass


@metadata.command()
@click.option('--db', type=click.Path(), required=True, help='Database path')
@click.option('--path', type=str, help='Filter files by path pattern (SQL LIKE)')
@click.option('--providers', default='spotify', help='Comma-separated list of providers')
@click.option('--limit', type=int, help='Maximum files to process')
@click.option('--force', is_flag=True, help='Re-enrich already-enriched files')
@click.option('--execute', is_flag=True, help='Actually update database (default: dry-run)')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def enrich(db, path, providers, limit, force, execute, verbose):
    """
    Enrich healthy files with metadata from external providers.

    Fetches BPM, key, genre, and other metadata from services like
    Spotify, Beatport, Qobuz, and Tidal. Uses ISRC and text search
    to identify tracks, then applies cascade rules to select the
    best values.

    \b
    Examples:
        # Dry-run on all eligible files
        dedupe metadata enrich --db music.db

        # Enrich files in a specific folder
        dedupe metadata enrich --db music.db --path "/Volumes/Music/DJ/%" --execute

        # Force re-enrich with multiple providers
        dedupe metadata enrich --db music.db --providers spotify,beatport --force --execute

        # Limit to 100 files for testing
        dedupe metadata enrich --db music.db --limit 100 --execute
    """
    from dedupe.metadata.enricher import Enricher
    from dedupe.metadata.auth import TokenManager
    from dedupe.storage.schema import init_db
    import sqlite3

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    db_path = Path(db)
    if not db_path.exists():
        raise click.ClickException(f"Database not found: {db_path}")

    # Ensure schema is up to date
    conn = sqlite3.connect(db_path)
    init_db(conn)
    conn.close()

    # Parse providers
    provider_list = [p.strip() for p in providers.split(',')]

    # Initialize token manager
    token_manager = TokenManager()

    # Check token status
    status = token_manager.status()
    for provider in provider_list:
        if provider in status:
            pstatus = status[provider]
            if not pstatus.get('configured'):
                click.echo(f"Warning: {provider} not configured in tokens.json")
            elif pstatus.get('expired'):
                click.echo(f"Warning: {provider} token expired, will attempt refresh")

    click.echo(f"\n{'='*50}")
    click.echo("METADATA ENRICHMENT")
    click.echo(f"{'='*50}")

    if not execute:
        click.echo("[DRY-RUN MODE - use --execute to update database]")

    click.echo(f"Database: {db_path}")
    click.echo(f"Providers: {', '.join(provider_list)}")
    if path:
        click.echo(f"Path filter: {path}")
    if limit:
        click.echo(f"Limit: {limit}")
    if force:
        click.echo("Force: re-enriching already-enriched files")

    def progress(current, total, filepath):
        if verbose:
            click.echo(f"[{current}/{total}] {filepath}")
        elif current % 10 == 0 or current == total:
            click.echo(f"Progress: {current}/{total}")

    with Enricher(
        db_path=db_path,
        token_manager=token_manager,
        providers=provider_list,
        dry_run=not execute,
    ) as enricher:
        stats = enricher.enrich_all(
            path_pattern=path,
            limit=limit,
            force=force,
            progress_callback=progress if not verbose else progress,
        )

    click.echo(f"\n{'='*50}")
    click.echo("RESULTS")
    click.echo(f"{'='*50}")
    click.echo(f"Total files:     {stats.total}")
    click.echo(f"Enriched:        {stats.enriched}")
    click.echo(f"No match:        {stats.no_match}")
    click.echo(f"Failed:          {stats.failed}")


@metadata.command()
@click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
def auth_status(tokens_path):
    """
    Show authentication status for all providers.

    Displays which providers are configured and whether their tokens
    are valid or expired.
    """
    from dedupe.metadata.auth import TokenManager, DEFAULT_TOKENS_PATH

    path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
    token_manager = TokenManager(path)

    click.echo(f"\nTokens file: {path}")
    click.echo(f"{'='*50}")

    status = token_manager.status()
    if not status:
        click.echo("No providers configured.")
        click.echo(f"\nRun 'dedupe metadata auth-init' to create a template.")
        return

    for provider, info in status.items():
        configured = "✓" if info.get('configured') else "✗"
        has_token = "✓" if info.get('has_token') else "✗"

        if info.get('expired') is True:
            token_status = "EXPIRED"
        elif info.get('has_token'):
            token_status = "valid"
        else:
            token_status = "missing"

        click.echo(f"{provider:12} | configured: {configured} | token: {has_token} ({token_status})")


@metadata.command()
@click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
def auth_init(tokens_path):
    """
    Initialize tokens.json with template structure.

    Creates a new tokens.json file with placeholders for all supported
    providers. You'll need to fill in your API credentials.
    """
    from dedupe.metadata.auth import TokenManager, DEFAULT_TOKENS_PATH

    path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
    token_manager = TokenManager(path)
    token_manager.init_template()

    click.echo(f"Created tokens template at: {path}")
    click.echo("\nEdit this file to add your API credentials:")
    click.echo("  - Spotify: client_id and client_secret")
    click.echo("  - Beatport: access_token")
    click.echo("  - Qobuz: app_id and user_auth_token")
    click.echo("  - Tidal: access_token")


@metadata.command()
@click.argument('provider')
@click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
def auth_refresh(provider, tokens_path):
    """
    Refresh access token for a provider.

    Currently supports automatic refresh for:
    - spotify (using client credentials flow)

    Other providers require manual token refresh.
    """
    from dedupe.metadata.auth import TokenManager, DEFAULT_TOKENS_PATH

    path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
    token_manager = TokenManager(path)

    if provider == 'spotify':
        click.echo("Refreshing Spotify token...")
        token = token_manager.refresh_spotify_token()
        if token:
            click.echo(f"Success! Token valid until: {token.expires_at}")
        else:
            click.echo("Failed to refresh token. Check client_id and client_secret.")
    else:
        click.echo(f"Automatic refresh not implemented for {provider}.")
        click.echo("Please update the token manually in tokens.json.")


if __name__ == "__main__":
    cli()
