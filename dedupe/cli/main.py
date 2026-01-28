import click
import logging
import sys
import time
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
    from legacy.tools.integrity.scan import scan as scan_cmd
    # If -h or --help is in args, we want to let the underlying command handle it
    # but Click might intercept it before we get here.
    # That's why we use help_option_names=[]
    sys.argv = ['dedupe scan'] + list(args)
    scan_cmd()


@cli.command(context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def recommend(args):
    """Generate deduplication recommendations (legacy wrapper)"""
    from legacy.tools.decide.recommend import recommend as recommend_cmd
    sys.argv = ['dedupe recommend'] + list(args)
    recommend_cmd()


@cli.command(context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def apply(args):
    """Execute deduplication plan (legacy wrapper)"""
    from legacy.tools.decide.apply import apply as apply_cmd
    sys.argv = ['dedupe apply'] + list(args)
    apply_cmd()


@cli.command("show-zone")
@click.argument("path", type=click.Path())
@click.option("--zones-config", type=click.Path(exists=True), help="Path to zones YAML config")
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config.toml")
def show_zone(path, zones_config, config):
    """Show how a path is classified by ZoneManager."""
    from dedupe.utils.config import get_config
    from dedupe.utils.zones import load_zone_manager

    cfg = get_config(Path(config)) if config else get_config()
    zone_manager = load_zone_manager(
        config=getattr(cfg, "_data", None),
        config_path=Path(zones_config) if zones_config else None,
    )
    match = zone_manager.get_zone_for_path(Path(path))

    click.echo(f"Path: {path}")
    click.echo(f"Zone: {match.zone.value}")
    click.echo(f"Zone priority: {match.zone_priority}")
    click.echo(f"Path priority: {match.path_priority}")
    click.echo(f"Matched root: {match.matched_path or '(none)'}")
    click.echo(f"Config source: {match.source}")


@cli.command("explain-keeper")
@click.option("--db", type=click.Path(), required=True, help="Database path")
@click.option("--group-id", required=True, help="Duplicate group id (checksum)")
@click.option("--zones-config", type=click.Path(exists=True), help="Path to zones YAML config")
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config.toml")
@click.option("--priority", "-p", multiple=True, help="Zone priority override order")
@click.option("--metadata-tiebreaker", is_flag=True, help="Enable metadata tiebreaker")
@click.option("--metadata-fields", default="artist,album,title", help="Comma-separated metadata fields")
def explain_keeper(db, group_id, zones_config, config, priority, metadata_tiebreaker, metadata_fields):
    """Explain keeper selection for a single duplicate group."""
    from dedupe.storage.schema import get_connection
    from dedupe.storage.queries import get_files_by_checksum
    from dedupe.storage.models import DuplicateGroup
    from dedupe.core.keeper_selection import select_keeper_for_group
    from dedupe.utils.zones import load_zone_manager
    from dedupe.utils.config import get_config

    cfg = get_config(Path(config)) if config else get_config()
    zone_manager = load_zone_manager(
        config=getattr(cfg, "_data", None),
        config_path=Path(zones_config) if zones_config else None,
    )
    if priority:
        zone_manager = zone_manager.override_priorities(list(priority))

    fields = [f.strip() for f in metadata_fields.split(",") if f.strip()]
    conn = get_connection(db, purpose="read")
    try:
        files = get_files_by_checksum(conn, group_id)
    finally:
        conn.close()

    if not files:
        raise click.ClickException(f"No files found for group id {group_id}")

    group = DuplicateGroup(group_id=group_id, files=files, similarity=1.0, source="checksum")
    selection = select_keeper_for_group(
        group,
        zone_manager=zone_manager,
        use_metadata_tiebreaker=metadata_tiebreaker,
        metadata_fields=tuple(fields),
    )

    click.echo(f"Group: {group_id}")
    click.echo(f"Keeper: {selection.keeper.path}")
    click.echo("-" * 60)
    for line in selection.explanations:
        click.echo(line)


@cli.command("enrich-file")
@click.option("--db", type=click.Path(), required=True, help="Database path")
@click.option("--file", "file_path", type=click.Path(), required=True, help="Exact file path in DB")
@click.option("--providers", default="beatport,spotify,tidal,qobuz,itunes", help="Comma-separated providers")
@click.option("--force", is_flag=True, help="Re-process even if already enriched")
@click.option("--retry-no-match", is_flag=True, help="Retry files previously with no match")
@click.option("--execute", is_flag=True, help="Write updates to DB (default: dry-run)")
@click.option("--recovery", is_flag=True, help="Recovery mode (duration health validation)")
@click.option("--hoarding", is_flag=True, help="Hoarding mode (full metadata)")
def enrich_file(db, file_path, providers, force, retry_no_match, execute, recovery, hoarding):
    """Enrich a single file by exact path."""
    from dedupe.metadata.enricher import Enricher
    from dedupe.metadata.auth import TokenManager
    from dedupe.storage.schema import init_db
    import sqlite3

    # Determine mode (default to recovery)
    if not recovery and not hoarding:
        recovery = True
    if recovery and hoarding:
        mode = "both"
    elif recovery:
        mode = "recovery"
    else:
        mode = "hoarding"

    # Ensure schema exists
    conn = sqlite3.connect(db)
    init_db(conn)
    conn.close()

    provider_list = [p.strip() for p in providers.split(",") if p.strip()]
    token_manager = TokenManager()

    click.echo(f"DB: {db}")
    click.echo(f"File: {file_path}")
    click.echo(f"Providers: {', '.join(provider_list)}")
    click.echo(f"Mode: {mode}")
    if not execute:
        click.echo("DRY-RUN: no DB updates will be written")

    with Enricher(
        db_path=Path(db),
        token_manager=token_manager,
        providers=provider_list,
        dry_run=not execute,
        mode=mode,
    ) as enricher:
        result, status = enricher.enrich_file(
            str(file_path),
            force=force,
            retry_no_match=retry_no_match,
        )

    if status == "not_found":
        raise click.ClickException("File not found in database")
    if status == "not_flac_ok":
        click.echo("Skipped: file failed integrity checks (use --force to override)")
        return
    if status == "not_eligible":
        click.echo("Skipped: already enriched (use --force or --retry-no-match)")
        return
    if status == "no_match":
        click.echo("No provider match found")
        return
    if status == "failed":
        click.echo("Enrichment failed to write to database")
        return

    if result and result.matches:
        best = max(result.matches, key=lambda m: m.match_confidence.value if m.match_confidence else 0)
        click.echo(f"Matched: {best.artist} - {best.title} ({best.service})")
        if result.canonical_isrc:
            click.echo(f"ISRC: {result.canonical_isrc}")
    click.echo("Done.")


@cli.command(context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def promote(args):
    """Promote files into canonical library layout (legacy wrapper)."""
    from legacy.tools.review.promote_by_tags import main as promote_cmd
    sys.argv = ['dedupe promote'] + list(args)
    promote_cmd()


@cli.group()
def quarantine():
    """Quarantine planning and apply commands."""
    pass


@quarantine.command(context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def plan(args):
    """Plan quarantine actions (legacy wrapper)."""
    from legacy.tools.review.plan_removals import main as plan_cmd
    sys.argv = ['dedupe quarantine plan'] + list(args)
    plan_cmd()


@quarantine.command("apply", context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def apply_quarantine(args):
    """Apply quarantine plan (legacy wrapper)."""
    from legacy.tools.review.apply_removals import main as apply_cmd
    sys.argv = ['dedupe quarantine apply'] + list(args)
    apply_cmd()


@quarantine.command(name="suspects", context_settings=dict(ignore_unknown_options=True, help_option_names=[]))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def quarantine_suspects(args):
    """Copy suspect/corrupt files to suspect zone (legacy wrapper)."""
    from legacy.tools.review.isolate_suspects import main as isolate_cmd
    sys.argv = ['dedupe quarantine suspects'] + list(args)
    isolate_cmd()

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
@click.option('--zones', type=str, help='Comma-separated zones to include (e.g. accepted,staging)')
@click.option('--providers', default='beatport,spotify,tidal,qobuz,itunes', help='Comma-separated list of providers (order = priority)')
@click.option('--limit', type=int, help='Maximum files to process')
@click.option('--force', is_flag=True, help='Re-process ALL already-processed files')
@click.option('--retry-no-match', is_flag=True, help='Retry files that had no provider match')
@click.option('--execute', is_flag=True, help='Actually update database (default: dry-run)')
@click.option('--recovery', is_flag=True, help='Recovery mode: focus on duration health validation')
@click.option('--hoarding', is_flag=True, help='Hoarding mode: collect full metadata (BPM, key, genre, etc.)')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def enrich(db, path, zones, providers, limit, force, retry_no_match, execute, recovery, hoarding, verbose):
    """
    Fetch metadata from external providers.

    Two modes available:

    \b
    --recovery  Health validation mode. Compares local file durations against
                provider durations to detect truncated or stitched files.
                Accepts lower-confidence matches. Sets metadata_health field.

    \b
    --hoarding  Full metadata mode. Fetches BPM, key, genre, label, artwork.
                Requires higher-confidence matches (ISRC or strong text match).
                Stores canonical values and raw provider data.

    If neither flag is specified, defaults to --recovery mode.

    \b
    Examples:
        # Recovery mode: validate health of recovered files
        dedupe metadata enrich --db music.db --recovery --execute

        # Hoarding mode: collect full metadata for DJ library
        dedupe metadata enrich --db music.db --hoarding --providers beatport,spotify --execute

        # Both modes: health check + full metadata
        dedupe metadata enrich --db music.db --recovery --hoarding --execute

        # Filter by path pattern
        dedupe metadata enrich --db music.db --recovery --path "/Volumes/Music/DJ/%" --execute
    """
    from dedupe.metadata.enricher import Enricher
    from dedupe.metadata.auth import TokenManager
    from dedupe.storage.schema import init_db
    import sqlite3
    from datetime import datetime

    # Set up logging to both file and console
    db_path = Path(db)
    log_dir = db_path.parent
    log_file = log_dir / f"enrich_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers = []

    # File handler - detailed logs (but not httpcore noise)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(file_handler)

    # Console handler - minimal (only warnings/errors unless verbose)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    root_logger.addHandler(console_handler)

    root_logger.setLevel(logging.DEBUG)

    # Silence noisy loggers
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Determine mode - default to recovery if neither specified
    if not recovery and not hoarding:
        recovery = True

    # Build mode string for enricher
    if recovery and hoarding:
        mode = "both"
    elif recovery:
        mode = "recovery"
    else:
        mode = "hoarding"

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

    click.echo("")
    click.echo("┌" + "─" * 50 + "┐")
    if mode == "recovery":
        click.echo("│  METADATA ENRICHMENT - Recovery Mode              │")
    elif mode == "hoarding":
        click.echo("│  METADATA ENRICHMENT - Hoarding Mode              │")
    else:
        click.echo("│  METADATA ENRICHMENT - Recovery + Hoarding        │")
    click.echo("└" + "─" * 50 + "┘")

    if not execute:
        click.echo("")
        click.echo("  ⚠  DRY-RUN MODE - use --execute to update database")

    click.echo("")
    click.echo(f"  Database:   {db_path}")
    click.echo(f"  Providers:  {' → '.join(provider_list)}")
    if path:
        click.echo(f"  Path:       {path}")
    if zones:
        click.echo(f"  Zones:      {zones}")
    if limit:
        click.echo(f"  Limit:      {limit}")
    if force:
        click.echo(f"  Mode:       Force (re-process ALL)")
    elif retry_no_match:
        click.echo(f"  Mode:       Retry (files with no previous match)")

    click.echo(f"  Log file:   {log_file}")
    click.echo("")
    click.echo("Resumable: Ctrl+C to pause, run again to continue")
    click.echo("")

    import shutil
    term_width = shutil.get_terminal_size().columns

    def progress(current, total, filepath):
        remaining = total - current
        pct = (current / total) * 100 if total > 0 else 0

        # Truncate filepath to fit terminal
        max_path_len = term_width - 45
        display_path = filepath
        if len(filepath) > max_path_len:
            display_path = "..." + filepath[-(max_path_len - 3):]

        # Simple progress line that updates in place
        status_line = f"\r[{current:>5}/{total}] {remaining:>5} left ({pct:5.1f}%) | {display_path}"
        click.echo(status_line.ljust(term_width)[:term_width], nl=False)

        # Print newline at end
        if current == total:
            click.echo("")

    with Enricher(
        db_path=db_path,
        token_manager=token_manager,
        providers=provider_list,
        dry_run=not execute,
        mode=mode,
    ) as enricher:
        zone_list = [z.strip() for z in zones.split(",")] if zones else None
        stats = enricher.enrich_all(
            path_pattern=path,
            limit=limit,
            force=force,
            retry_no_match=retry_no_match,
            zones=zone_list,
            progress_callback=progress,
        )

    click.echo("")
    click.echo(f"{'='*50}")
    click.echo("RESULTS")
    click.echo(f"{'='*50}")
    click.echo(f"  Total:      {stats.total:>6}")
    click.echo(f"  Enriched:   {stats.enriched:>6}  ✓")
    click.echo(f"  No match:   {stats.no_match:>6}")
    click.echo(f"  Failed:     {stats.failed:>6}  {'⚠' if stats.failed > 0 else ''}")

    # Show sample of no-match files
    if stats.no_match_files:
        click.echo("")
        click.echo("NO MATCH (sample):")
        for path in stats.no_match_files[:10]:
            # Show just the filename
            click.echo(f"  • {Path(path).name}")
        if len(stats.no_match_files) > 10:
            click.echo(f"  ... and {len(stats.no_match_files) - 10} more")

    click.echo("")
    click.echo(f"Full log: {log_file}")


@metadata.command()
@click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
@click.option('--no-refresh', is_flag=True, help='Skip auto-refresh of tokens')
def auth_status(tokens_path, no_refresh):
    """
    Show authentication status for all providers.

    Displays which providers are configured and whether their tokens
    are valid or expired. Automatically refreshes tokens for providers
    that support it.
    """
    from dedupe.metadata.auth import TokenManager, DEFAULT_TOKENS_PATH

    path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
    token_manager = TokenManager(path)

    click.echo(f"\nTokens file: {path}")
    click.echo("=" * 60)

    # Auto-refresh tokens for providers that support it
    if not no_refresh:
        # Spotify - client credentials
        if token_manager.is_configured("spotify"):
            token = token_manager.get_token("spotify")
            if token is None or token.is_expired:
                click.echo("Refreshing Spotify token...")
                token_manager.refresh_spotify_token()

        # Beatport - client credentials
        if token_manager.is_configured("beatport"):
            token = token_manager.get_token("beatport")
            if token is None or token.is_expired:
                click.echo("Refreshing Beatport token...")
                token_manager.refresh_beatport_token()

        # Tidal - refresh token (only if already authenticated)
        if token_manager.is_configured("tidal"):
            token = token_manager.get_token("tidal")
            if token is None or token.is_expired:
                click.echo("Refreshing Tidal token...")
                token_manager.refresh_tidal_token()

    status = token_manager.status()

    for provider, info in status.items():
        configured = "✓" if info.get('configured') else "✗"
        has_token = "✓" if info.get('has_token') else "✗"
        auth_type = info.get('auth_type', '')

        if provider == "itunes":
            token_status = "ready (no auth needed)"
        elif info.get('expired') is True:
            token_status = "EXPIRED"
        elif info.get('has_token'):
            token_status = "valid"
        else:
            token_status = "not authenticated"

        click.echo(f"{provider:12} | {configured} configured | {has_token} token ({token_status})")

    # Show help for unconfigured providers
    click.echo("")
    unconfigured = [p for p, info in status.items() if not info.get('configured') and p != 'itunes']
    if unconfigured:
        click.echo("To configure providers:")
        if 'spotify' in unconfigured:
            click.echo("  spotify:  Add client_id/client_secret to tokens.json")
            click.echo("            (get from https://developer.spotify.com/dashboard)")
        if 'beatport' in unconfigured:
            click.echo("  beatport: Run 'dedupe metadata auth-login beatport'")
            click.echo("            (paste token from dj.beatport.com DevTools)")
        if 'tidal' in unconfigured:
            click.echo("  tidal:    Run 'dedupe metadata auth-login tidal'")
        if 'qobuz' in unconfigured:
            click.echo("  qobuz:    Run 'dedupe metadata auth-login qobuz'")


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
    click.echo("\nNext steps:")
    click.echo("  1. Spotify/Beatport: Edit tokens.json to add client_id and client_secret")
    click.echo("  2. Tidal: Run 'dedupe metadata auth-login tidal'")
    click.echo("  3. Qobuz: Run 'dedupe metadata auth-login qobuz'")
    click.echo("  4. iTunes: No setup needed (public API)")


@metadata.command()
@click.argument('provider')
@click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
def auth_refresh(provider, tokens_path):
    """
    Refresh access token for a provider.

    Supports automatic refresh for:
    - spotify (client credentials)
    - beatport (client credentials)
    - tidal (refresh token, requires prior auth-login)
    """
    from dedupe.metadata.auth import TokenManager, DEFAULT_TOKENS_PATH

    path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
    token_manager = TokenManager(path)

    if provider == 'spotify':
        click.echo("Refreshing Spotify token...")
        token = token_manager.refresh_spotify_token()
        if token:
            click.echo(f"Success! Token expires at: {time.ctime(token.expires_at)}")
        else:
            click.echo("Failed. Check client_id and client_secret in tokens.json")

    elif provider == 'beatport':
        token = token_manager.refresh_beatport_token()
        if token and not token.is_expired:
            click.echo(f"Beatport token valid until: {time.ctime(token.expires_at)}")
        else:
            click.echo("Beatport token expired or missing.")
            click.echo("Run 'dedupe metadata auth-login beatport' to set a new token.")

    elif provider == 'tidal':
        click.echo("Refreshing Tidal token...")
        token = token_manager.refresh_tidal_token()
        if token:
            click.echo(f"Success! Token expires at: {time.ctime(token.expires_at)}")
        else:
            click.echo("Failed. Run 'dedupe metadata auth-login tidal' first.")

    elif provider == 'qobuz':
        click.echo("Qobuz tokens don't expire. Run 'dedupe metadata auth-login qobuz' to re-authenticate.")

    else:
        click.echo(f"Unknown provider: {provider}")


@metadata.command()
@click.argument('provider')
@click.option('--tokens-path', type=click.Path(), help='Path to tokens.json')
def auth_login(provider, tokens_path):
    """
    Authenticate with a provider interactively.

    Supported providers:
    - tidal: Device authorization (opens browser)
    - qobuz: Email/password login
    - beatport: Manual token from browser DevTools
    """
    from dedupe.metadata.auth import TokenManager, DEFAULT_TOKENS_PATH

    path = Path(tokens_path) if tokens_path else DEFAULT_TOKENS_PATH
    token_manager = TokenManager(path)

    if provider == 'tidal':
        _tidal_device_login(token_manager)

    elif provider == 'qobuz':
        _qobuz_login(token_manager)

    elif provider == 'beatport':
        _beatport_token_input(token_manager)

    else:
        click.echo(f"Interactive login not supported for {provider}.")
        click.echo("For Spotify, add client_id and client_secret to tokens.json")


def _tidal_device_login(token_manager):
    """Handle Tidal device authorization flow."""
    click.echo("Starting Tidal device authorization...")

    device_auth = token_manager.start_tidal_device_auth()
    if not device_auth:
        click.echo("Failed to start device authorization.")
        return

    user_code = device_auth.get("userCode")
    verification_uri = device_auth.get("verificationUriComplete") or device_auth.get("verificationUri")
    device_code = device_auth.get("deviceCode")
    expires_in = device_auth.get("expiresIn", 300)
    interval = device_auth.get("interval", 5)

    click.echo(f"\n1. Go to: {verification_uri}")
    if user_code:
        click.echo(f"2. Enter code: {user_code}")
    click.echo(f"\nWaiting for authorization (expires in {expires_in}s)...")

    # Poll for completion
    start_time = time.time()
    while time.time() - start_time < expires_in:
        time.sleep(interval)

        token = token_manager.complete_tidal_device_auth(device_code)
        if token:
            click.echo("\nTidal authentication successful!")
            click.echo(f"Token expires at: {time.ctime(token.expires_at)}")
            return

        # Show progress
        elapsed = int(time.time() - start_time)
        click.echo(f"  Waiting... ({elapsed}s)", nl=False)
        click.echo("\r", nl=False)

    click.echo("\nAuthorization timed out. Please try again.")


def _qobuz_login(token_manager):
    """Handle Qobuz email/password login."""
    click.echo("Qobuz Login")
    click.echo("-" * 40)

    email = click.prompt("Email")
    password = click.prompt("Password", hide_input=True)

    click.echo("\nLogging in...")
    token = token_manager.login_qobuz(email, password)

    if token:
        click.echo("Qobuz authentication successful!")
    else:
        click.echo("Login failed. Check your email and password.")


def _beatport_token_input(token_manager):
    """Handle manual Beatport token input."""
    click.echo("Beatport Token Setup")
    click.echo("-" * 40)
    click.echo("Beatport requires manual token extraction from the browser.")
    click.echo("")
    click.echo("Steps:")
    click.echo("  1. Go to https://dj.beatport.com in your browser")
    click.echo("  2. Open DevTools (F12) -> Network tab")
    click.echo("  3. Look for any request to api.beatport.com")
    click.echo("  4. Find the 'Authorization: Bearer ...' header")
    click.echo("  5. Copy the token (everything after 'Bearer ')")
    click.echo("")
    click.echo("Note: These tokens expire every ~10 minutes.")
    click.echo("")

    token = click.prompt("Paste Bearer token (or 'skip' to cancel)")

    if token.lower() == 'skip':
        click.echo("Skipped.")
        return

    # Clean up token if user included "Bearer " prefix
    if token.lower().startswith("bearer "):
        token = token[7:]

    # Try to decode JWT to get expiration
    expires_at = None
    try:
        import base64
        import json
        # JWT is header.payload.signature
        parts = token.split('.')
        if len(parts) == 3:
            # Decode payload (add padding if needed)
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += '=' * padding
            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)
            expires_at = data.get('exp')
    except Exception:
        pass

    token_manager.set_token(
        "beatport",
        access_token=token,
        expires_at=expires_at,
    )

    if expires_at:
        click.echo(f"Beatport token saved! Expires at: {time.ctime(expires_at)}")
    else:
        click.echo("Beatport token saved! (couldn't determine expiration)")


if __name__ == "__main__":
    cli()
