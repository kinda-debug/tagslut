import click
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path so we can import tools as modules if needed
sys.path.insert(0, str(Path(__file__).parents[2]))
_PROJECT_ROOT = Path(__file__).parents[2]

logger = logging.getLogger("dedupe")

_TRANSITIONAL_COMMAND_REPLACEMENTS: dict[str, str] = {
    "dedupe _mgmt": "tagslut index ... / tagslut report m3u ...",
    "dedupe _metadata": "tagslut auth ... / tagslut index enrich ...",
    "dedupe _recover": "tagslut verify recovery ... / tagslut report recovery ...",
}
_INTERNAL_CLI_ENV = "DEDUPE_CLI_INTERNAL_CALL"
_DEDUPE_ALIAS_RETIRE_AFTER = datetime(2026, 7, 31).date()


def _format_transitional_warning(command: str) -> str:
    replacement = _TRANSITIONAL_COMMAND_REPLACEMENTS.get(command)
    message = (
        f"DEPRECATION NOTICE: '{command}' is a transitional legacy wrapper. "
        "Use canonical entrypoints from docs/SCRIPT_SURFACE.md."
    )
    if replacement:
        message += f" Recommended now: `{replacement}`."
    return message


def _warn_transitional_command(command: str) -> None:
    click.secho(_format_transitional_warning(command), fg="yellow", err=True)


def _is_internal_cli_call() -> bool:
    return os.getenv(_INTERNAL_CLI_ENV) == "1"


def _format_dedupe_alias_warning(argv0: str | None = None) -> str | None:
    invoked = (argv0 or Path(sys.argv[0]).name).strip().lower()
    if invoked != "dedupe":
        return None

    today = datetime.now(UTC).date()
    retirement = _DEDUPE_ALIAS_RETIRE_AFTER.strftime("%B %d, %Y")
    if today <= _DEDUPE_ALIAS_RETIRE_AFTER:
        return (
            "ALIAS DEPRECATION: 'dedupe' is a compatibility alias and is scheduled "
            f"for retirement after {retirement}. Use 'tagslut' for all new commands."
        )
    return (
        "ALIAS DEPRECATION: 'dedupe' is past its planned retirement window "
        f"({retirement}). Switch to 'tagslut' immediately."
    )


class _TagslutGroup(click.Group):
    """CLI group that can emit alias warnings before help handling."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not _is_internal_cli_call():
            warning = _format_dedupe_alias_warning(ctx.info_name)
            if warning:
                click.secho(warning, fg="yellow", err=True)
        return super().parse_args(ctx, args)


def _run_subprocess(cmd: list[str], *, internal: bool = False) -> None:
    import subprocess

    env = os.environ.copy()
    if internal:
        env[_INTERNAL_CLI_ENV] = "1"
    proc = subprocess.run(cmd, cwd=_PROJECT_ROOT, env=env, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def _run_dedupe_wrapper(args: list[str]) -> None:
    _run_subprocess([sys.executable, "-m", "dedupe", *args], internal=True)


def _run_python_script(script_rel_path: str, args: tuple[str, ...]) -> None:
    script_path = (_PROJECT_ROOT / script_rel_path).resolve()
    _run_subprocess([sys.executable, str(script_path), *list(args)], internal=True)


def _run_executable(script_rel_path: str, args: tuple[str, ...]) -> None:
    script_path = (_PROJECT_ROOT / script_rel_path).resolve()
    _run_subprocess([str(script_path), *list(args)], internal=True)


def _collect_flac_paths(input_path: str) -> list[Path]:
    path = Path(input_path).expanduser().resolve()
    if path.is_dir():
        from dedupe.utils.paths import list_files
        files = list(list_files(path, {".flac"}))
        return sorted(files, key=lambda p: str(p))
    if path.is_file():
        return [path]
    raise click.ClickException(f"Path not found: {input_path}")


def _local_file_info_from_path(file_path: Path):
    from dedupe.core.metadata import extract_metadata
    from dedupe.metadata.models.types import LocalFileInfo

    audio = extract_metadata(file_path, scan_integrity=False, scan_hash=False)
    tags = audio.metadata or {}

    def get_tag(key: str):
        val = tags.get(key)
        if isinstance(val, list) and val:
            return str(val[0])
        if val is not None:
            return str(val)
        return None

    def get_int_tag(key: str) -> int | None:
        val = get_tag(key)
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return None

    return LocalFileInfo(
        path=str(audio.path),
        measured_duration_s=audio.duration or None,
        tag_artist=get_tag("artist") or get_tag("albumartist"),
        tag_title=get_tag("title"),
        tag_album=get_tag("album"),
        tag_isrc=get_tag("isrc"),
        tag_label=get_tag("label") or get_tag("organization"),
        tag_year=get_int_tag("date") or get_int_tag("year"),
    )


def _print_enrichment_result(result) -> None:
    if not result or not result.matches:
        click.echo("No provider match found")
        return
    best = max(result.matches, key=lambda m: m.match_confidence.value if m.match_confidence else 0)
    click.echo(f"Matched: {best.artist} - {best.title} ({best.service})")
    if result.canonical_isrc:
        click.echo(f"ISRC: {result.canonical_isrc}")
    if result.canonical_bpm:
        click.echo(f"BPM: {result.canonical_bpm}")
    if result.canonical_key:
        click.echo(f"Key: {result.canonical_key}")
    if result.canonical_genre:
        click.echo(f"Genre: {result.canonical_genre}")


@click.group(cls=_TagslutGroup)
@click.version_option(version="2.0.0")
def cli():
    """Tagslut CLI (dedupe compatibility alias preserved)."""


def _default_canon_rules_path() -> Path:
    return Path(__file__).parents[2] / "tools" / "rules" / "library_canon.json"


@cli.command("canonize")
@click.argument("path", type=click.Path(exists=True))
@click.option("--canon/--no-canon", default=True, help="Enable canonical tag rules")
@click.option("--canon-rules", type=click.Path(exists=True), help="Path to canon rules JSON")
@click.option("--canon-dry-run", is_flag=True, help="Print before/after diff for one file and exit")
@click.option("--execute", is_flag=True, help="Write tags to files (default: dry-run)")
@click.option("--limit", type=int, help="Maximum files to process")
def canonize(path, canon, canon_rules, canon_dry_run, execute, limit):
    """Apply canonical tag rules to FLAC tags using library_canon.json."""
    from mutagen.flac import FLAC
    from dedupe.metadata.canon import load_canon_rules, apply_canon, canon_diff

    rules_path = Path(canon_rules) if canon_rules else _default_canon_rules_path()
    rules = load_canon_rules(rules_path)

    file_paths = _collect_flac_paths(path)
    if limit:
        file_paths = file_paths[:limit]
    if not file_paths:
        click.echo("No FLAC files found.")
        return

    if canon_dry_run:
        target = file_paths[0]
        audio = FLAC(target)
        before = {k: list(v) if isinstance(v, list) else v for k, v in audio.tags.items()}
        after = apply_canon(before, rules) if canon else before
        diff = canon_diff(before, after)
        click.echo(diff or "(no changes)")
        return

    if not execute:
        click.echo("DRY-RUN: use --execute to write tags")

    for idx, file_path in enumerate(file_paths, start=1):
        audio = FLAC(file_path)
        before = {k: list(v) if isinstance(v, list) else v for k, v in audio.tags.items()}
        after = apply_canon(before, rules) if canon else before
        if execute:
            audio.clear()
            for key, value in after.items():
                if isinstance(value, (list, tuple)):
                    audio[key] = [str(v) for v in value]
                else:
                    audio[key] = str(value)
            audio.save()
        if idx % 250 == 0 or idx == len(file_paths):
            click.echo(f"Processed {idx}/{len(file_paths)}")


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
@click.option("--db", type=click.Path(), required=False, help="Database path")
@click.option("--file", "file_path", type=click.Path(), required=True, help="Exact file path in DB (or on disk in --standalone mode)")
@click.option("--providers", default="beatport,spotify,tidal,qobuz,itunes", help="Comma-separated providers")
@click.option("--force", is_flag=True, help="Re-process even if already enriched")
@click.option("--retry-no-match", is_flag=True, help="Retry files previously with no match")
@click.option("--execute", is_flag=True, help="Write updates to DB (default: dry-run)")
@click.option("--recovery", is_flag=True, help="Recovery mode (duration health validation)")
@click.option("--hoarding", is_flag=True, help="Hoarding mode (full metadata)")
@click.option("--standalone", is_flag=True, help="Run without a database (read tags directly)")
def enrich_file(db, file_path, providers, force, retry_no_match, execute, recovery, hoarding, standalone):
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

    provider_list = [p.strip() for p in providers.split(",") if p.strip()]
    token_manager = TokenManager()

    if standalone:
        if db:
            raise click.ClickException("--standalone cannot be used with --db")
        file_path_obj = Path(file_path).expanduser().resolve()
        if not file_path_obj.exists():
            raise click.ClickException(f"File not found: {file_path}")
        if execute:
            click.echo("Note: --execute is ignored in standalone mode (no DB writes).")
        click.echo(f"File: {file_path_obj}")
        click.echo(f"Providers: {', '.join(provider_list)}")
        click.echo(f"Mode: {mode}")
        with Enricher(
            db_path=Path("__standalone__"),
            token_manager=token_manager,
            providers=provider_list,
            dry_run=True,
            mode=mode,
        ) as enricher:
            try:
                file_info = _local_file_info_from_path(file_path_obj)
            except Exception as e:
                raise click.ClickException(str(e)) from e
            result = enricher.resolve_file(file_info)
        _print_enrichment_result(result)
        click.echo("Done.")
        return

    if not db:
        raise click.ClickException("--db is required (or use --standalone)")

    # Ensure schema exists
    conn = sqlite3.connect(db)
    init_db(conn)
    conn.close()

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

    _print_enrichment_result(result)
    click.echo("Done.")


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

    # Backups (external)
    click.echo("\n3. BACKUPS")
    click.echo("   Backups are handled externally (Time Machine/NAS).")
    click.echo("   This tool does not create or retain backups.")
    config["backup_dir"] = None

    # Output report
    click.echo("\n4. OUTPUT REPORT")
    click.echo("   Where to save the final recovery report.")
    default_output = Path.cwd() / "recovery_report.csv"
    output = click.prompt("   Enter report output path", default=str(default_output), type=str)
    config["output"] = Path(output).expanduser().resolve()
    click.echo(f"   -> {config['output']}")

    # Workers
    click.echo("\n5. PARALLEL WORKERS")
    workers = click.prompt("   Number of parallel scan workers", default=4, type=int)
    config["workers"] = workers
    click.echo(f"   -> {workers} workers")

    # Confirmation
    click.echo("\n" + "=" * 60)
    click.echo("CONFIGURATION SUMMARY")
    click.echo("=" * 60)
    click.echo(f"  Source:     {config['source']}")
    click.echo(f"  Database:   {config['db']}")
    click.echo("  Backups:    external-only (no local backups)")
    click.echo(f"  Output:     {config['output']}")
    click.echo(f"  Workers:    {config['workers']}")
    click.echo("=" * 60)

    if not click.confirm("\nProceed with these settings?", default=True):
        raise click.Abort()

    return config


@cli.command("init")
@click.option('--output-format', type=click.Choice(['env', 'toml', 'both']), default='env', help='Configuration output format')
@click.option('--output-path', type=click.Path(), help='Custom path for config file')
@click.option('--setup-tokens', is_flag=True, help='Also initialize tokens.json for metadata providers')
def init(output_format, output_path, setup_tokens):
    """
    Interactive initialization wizard for dedupe configuration.

    Prompts for all necessary paths, settings, and credentials needed
    for scanning and managing your music library.

    Generates configuration in .env or config.toml format.
    """
    from dedupe.metadata.auth import TokenManager, DEFAULT_TOKENS_PATH
    import os

    click.echo("")
    click.echo("╔" + "═" * 58 + "╗")
    click.echo("║" + "  DEDUPE INITIALIZATION WIZARD".center(58) + "║")
    click.echo("╚" + "═" * 58 + "╝")
    click.echo("")
    click.echo("This wizard will help you configure dedupe for your music library.")
    click.echo("You can skip optional settings by pressing Enter.")
    click.echo("")

    config = {}

    # ========================================================================
    # SECTION 1: DATABASE
    # ========================================================================
    click.echo("─" * 60)
    click.echo("1. DATABASE CONFIGURATION")
    click.echo("─" * 60)
    click.echo("The database stores scan results, integrity checks, and metadata.")
    click.echo("")

    default_db = str(Path.home() / "dedupe" / "music.db")
    db_path = click.prompt("Database path", default=default_db, type=str)
    config["DEDUPE_DB"] = Path(db_path).expanduser().resolve()

    # Create parent directory if needed
    if click.confirm(f"Create database directory if it doesn't exist?", default=True):
        config["DEDUPE_DB"].parent.mkdir(parents=True, exist_ok=True)
        click.echo(f"  ✓ Ensured directory exists: {config['DEDUPE_DB'].parent}")

    click.echo("")

    # ========================================================================
    # SECTION 2: VOLUME PATHS
    # ========================================================================
    click.echo("─" * 60)
    click.echo("2. VOLUME PATHS")
    click.echo("─" * 60)
    click.echo("Volumes are physical directories where your music files are stored.")
    click.echo("Zones are logical categories (e.g., accepted, staging, quarantine).")
    click.echo("")

    # Required: Library volume
    click.echo("PRIMARY LIBRARY (required)")
    click.echo("  Main collection of accepted/canonical music files")
    while True:
        library = click.prompt("  Library path", type=str)
        library_path = Path(library).expanduser().resolve()
        if library_path.is_dir():
            config["VOLUME_LIBRARY"] = library_path
            click.echo(f"  ✓ {library_path}")
            break
        click.echo(f"  ✗ Directory not found: {library}. Try again.")
    click.echo("")

    # Optional volumes
    optional_volumes = {
        "VOLUME_STAGING": ("Staging area", "Files being processed/reviewed"),
        "VOLUME_ARCHIVE": ("Archive", "Historical backups or older versions"),
        "VOLUME_INBOX": ("Inbox", "New/incoming files to be processed"),
        "VOLUME_SUSPECT": ("Suspect", "Files with integrity issues"),
        "VOLUME_REJECTED": ("Rejected", "Rejected/unwanted files"),
        "VOLUME_QUARANTINE": ("Quarantine", "Files marked for deletion"),
        "VOLUME_RECOVERY": ("Recovery", "Recovery target for salvaged files"),
        "VOLUME_VAULT": ("Vault", "External backup/vault location"),
    }

    for var_name, (short_name, description) in optional_volumes.items():
        click.echo(f"{short_name.upper()} (optional)")
        click.echo(f"  {description}")
        volume = click.prompt(f"  {short_name} path (press Enter to skip)", default="", type=str)
        if volume:
            volume_path = Path(volume).expanduser().resolve()
            if volume_path.is_dir():
                config[var_name] = volume_path
                click.echo(f"  ✓ {volume_path}")
            else:
                click.echo(f"  ⚠ Directory not found: {volume} (skipped)")
        click.echo("")

    # ========================================================================
    # SECTION 3: OUTPUT DIRECTORIES
    # ========================================================================
    click.echo("─" * 60)
    click.echo("3. OUTPUT DIRECTORIES")
    click.echo("─" * 60)
    click.echo("Where to save reports, logs, and artifacts.")
    click.echo("")

    default_artifacts = str(Path.cwd() / "artifacts")
    artifacts = click.prompt("Artifacts directory", default=default_artifacts, type=str)
    config["DEDUPE_ARTIFACTS"] = Path(artifacts).expanduser().resolve()

    default_reports = str(config["DEDUPE_ARTIFACTS"] / "reports")
    reports = click.prompt("Reports directory", default=default_reports, type=str)
    config["DEDUPE_REPORTS"] = Path(reports).expanduser().resolve()

    # Create directories
    if click.confirm("Create output directories if they don't exist?", default=True):
        config["DEDUPE_ARTIFACTS"].mkdir(parents=True, exist_ok=True)
        config["DEDUPE_REPORTS"].mkdir(parents=True, exist_ok=True)
        click.echo(f"  ✓ Created: {config['DEDUPE_ARTIFACTS']}")
        click.echo(f"  ✓ Created: {config['DEDUPE_REPORTS']}")

    click.echo("")

    # ========================================================================
    # SECTION 4: SCAN SETTINGS
    # ========================================================================
    click.echo("─" * 60)
    click.echo("4. SCAN SETTINGS")
    click.echo("─" * 60)
    click.echo("Performance and validation options for scanning.")
    click.echo("")

    import os
    cpu_count = os.cpu_count() or 4
    recommended_workers = max(4, cpu_count - 2)

    workers = click.prompt(
        f"Parallel workers (CPU cores: {cpu_count}, recommended: {recommended_workers})",
        default=recommended_workers,
        type=int
    )
    config["SCAN_WORKERS"] = workers

    check_integrity = click.confirm(
        "Run FLAC integrity checks (flac -t)? Slower but thorough",
        default=True
    )
    config["SCAN_CHECK_INTEGRITY"] = check_integrity

    check_hash = click.confirm(
        "Calculate SHA256 hashes? Slower but enables deduplication",
        default=True
    )
    config["SCAN_CHECK_HASH"] = check_hash

    incremental = click.confirm(
        "Use incremental scanning? (Skip already-scanned files)",
        default=True
    )
    config["SCAN_INCREMENTAL"] = incremental

    progress_interval = click.prompt(
        "Progress report interval (files)",
        default=100,
        type=int
    )
    config["SCAN_PROGRESS_INTERVAL"] = progress_interval

    click.echo("")

    # ========================================================================
    # SECTION 5: DECISION SETTINGS
    # ========================================================================
    click.echo("─" * 60)
    click.echo("5. DECISION SETTINGS")
    click.echo("─" * 60)
    click.echo("Preferences for duplicate resolution and quality.")
    click.echo("")

    auto_approve = click.prompt(
        "Auto-approve threshold (0.0-1.0, higher = more conservative)",
        default=0.95,
        type=float
    )
    config["AUTO_APPROVE_THRESHOLD"] = auto_approve

    quarantine_days = click.prompt(
        "Quarantine retention days (before eligible for deletion)",
        default=30,
        type=int
    )
    config["QUARANTINE_RETENTION_DAYS"] = quarantine_days

    config["PREFER_HIGH_BITRATE"] = click.confirm(
        "Prefer high bitrate when deduplicating?",
        default=True
    )

    config["PREFER_HIGH_SAMPLE_RATE"] = click.confirm(
        "Prefer high sample rate when deduplicating?",
        default=True
    )

    config["PREFER_VALID_INTEGRITY"] = click.confirm(
        "Prefer files with valid integrity?",
        default=True
    )

    click.echo("")

    # ========================================================================
    # SECTION 6: METADATA PROVIDERS (OPTIONAL)
    # ========================================================================
    if setup_tokens or click.confirm("Configure metadata providers for enrichment?", default=False):
        click.echo("")
        click.echo("─" * 60)
        click.echo("6. METADATA PROVIDER AUTHENTICATION")
        click.echo("─" * 60)
        click.echo("External services for fetching BPM, key, genre, ISRC, etc.")
        click.echo("")

        token_manager = TokenManager()

        # Initialize tokens file if needed
        if not DEFAULT_TOKENS_PATH.exists():
            token_manager.init_template()
            click.echo(f"✓ Created tokens template: {DEFAULT_TOKENS_PATH}")

        click.echo("Available providers:")
        click.echo("  • Spotify    - Client credentials (get from developer.spotify.com)")
        click.echo("  • Beatport   - Manual token extraction (requires DJ account)")
        click.echo("  • Tidal      - Device authorization (requires subscription)")
        click.echo("  • Qobuz      - Email/password login (requires account)")
        click.echo("  • iTunes     - No authentication needed (public API)")
        click.echo("")

        if click.confirm("Set up Spotify?", default=False):
            click.echo("Get credentials from: https://developer.spotify.com/dashboard")
            client_id = click.prompt("  Spotify Client ID", type=str)
            client_secret = click.prompt("  Spotify Client Secret", type=str, hide_input=True)
            # Update Spotify credentials in tokens
            if "spotify" not in token_manager._tokens:
                token_manager._tokens["spotify"] = {}
            token_manager._tokens["spotify"]["client_id"] = client_id
            token_manager._tokens["spotify"]["client_secret"] = client_secret
            token_manager._save_tokens()
            click.echo("  ✓ Spotify configured")
            click.echo("")

        if click.confirm("Set up Tidal?", default=False):
            _tidal_device_login(token_manager)
            click.echo("")

        if click.confirm("Set up Qobuz?", default=False):
            _qobuz_login(token_manager)
            click.echo("")

        if click.confirm("Set up Beatport?", default=False):
            _beatport_token_input(token_manager)
            click.echo("")

        click.echo(f"✓ Token configuration saved to: {DEFAULT_TOKENS_PATH}")
        click.echo("")

    # ========================================================================
    # SUMMARY & CONFIRMATION
    # ========================================================================
    click.echo("═" * 60)
    click.echo("CONFIGURATION SUMMARY")
    click.echo("═" * 60)
    click.echo("")
    click.echo("DATABASE:")
    click.echo(f"  {config['DEDUPE_DB']}")
    click.echo("")
    click.echo("VOLUMES:")
    for key, value in config.items():
        if key.startswith("VOLUME_"):
            zone_name = key.replace("VOLUME_", "").lower().title()
            click.echo(f"  {zone_name:12} → {value}")
    click.echo("")
    click.echo("OUTPUT:")
    click.echo(f"  Artifacts    → {config['DEDUPE_ARTIFACTS']}")
    click.echo(f"  Reports      → {config['DEDUPE_REPORTS']}")
    click.echo("")
    click.echo("SCAN SETTINGS:")
    click.echo(f"  Workers:     {config['SCAN_WORKERS']}")
    click.echo(f"  Integrity:   {config['SCAN_CHECK_INTEGRITY']}")
    click.echo(f"  Hash:        {config['SCAN_CHECK_HASH']}")
    click.echo(f"  Incremental: {config['SCAN_INCREMENTAL']}")
    click.echo("")
    click.echo("DECISION SETTINGS:")
    click.echo(f"  Auto-approve:    {config['AUTO_APPROVE_THRESHOLD']}")
    click.echo(f"  Quarantine days: {config['QUARANTINE_RETENTION_DAYS']}")
    click.echo(f"  Prefer hi-res:   {config['PREFER_HIGH_BITRATE']} / {config['PREFER_HIGH_SAMPLE_RATE']}")
    click.echo("")
    click.echo("═" * 60)

    if not click.confirm("Save this configuration?", default=True):
        click.echo("Aborted.")
        raise click.Abort()

    # ========================================================================
    # WRITE CONFIGURATION
    # ========================================================================
    click.echo("")

    if output_format in ('env', 'both'):
        env_path = Path(output_path) if output_path and output_format == 'env' else Path.cwd() / ".env"
        _write_env_file(config, env_path)
        click.echo(f"✓ Saved environment config: {env_path}")
        click.echo("")
        click.echo("To use this configuration:")
        click.echo(f"  export $(cat {env_path} | xargs)")
        click.echo("  OR add to your ~/.bashrc or ~/.zshrc:")
        click.echo(f"  source {env_path}")
        click.echo("")

    if output_format in ('toml', 'both'):
        toml_path = Path(output_path) if output_path and output_format == 'toml' else Path.cwd() / "config.toml"
        _write_toml_file(config, toml_path)
        click.echo(f"✓ Saved TOML config: {toml_path}")
        click.echo("")
        click.echo("To use this configuration:")
        click.echo(f"  export DEDUPE_CONFIG={toml_path}")
        click.echo("")

    click.echo("═" * 60)
    click.echo("INITIALIZATION COMPLETE!")
    click.echo("═" * 60)
    click.echo("")
    click.echo("Next steps:")
    click.echo("  1. Review your configuration file")
    click.echo("  2. Register/index your library:")
    click.echo(f"     tagslut index register {config['VOLUME_LIBRARY']} --source legacy")
    click.echo("  3. Build a deterministic plan:")
    click.echo("     tagslut decide plan --policy library_balanced --input candidates.json")
    click.echo("")


def _write_env_file(config: dict, path: Path) -> None:
    """Write configuration as .env file."""
    lines = [
        "# Dedupe Configuration",
        "# Generated by: dedupe init",
        f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "# ============================================================================",
        "# DATABASE",
        "# ============================================================================",
        f"DEDUPE_DB={config['DEDUPE_DB']}",
        "",
        "# ============================================================================",
        "# VOLUMES",
        "# ============================================================================",
    ]

    for key, value in sorted(config.items()):
        if key.startswith("VOLUME_"):
            lines.append(f"{key}={value}")

    lines.extend([
        "",
        "# ============================================================================",
        "# OUTPUT DIRECTORIES",
        "# ============================================================================",
        f"DEDUPE_ARTIFACTS={config['DEDUPE_ARTIFACTS']}",
        f"DEDUPE_REPORTS={config['DEDUPE_REPORTS']}",
        "",
        "# ============================================================================",
        "# SCAN SETTINGS",
        "# ============================================================================",
        f"SCAN_WORKERS={config['SCAN_WORKERS']}",
        f"SCAN_PROGRESS_INTERVAL={config['SCAN_PROGRESS_INTERVAL']}",
        f"SCAN_CHECK_INTEGRITY={str(config['SCAN_CHECK_INTEGRITY']).lower()}",
        f"SCAN_CHECK_HASH={str(config['SCAN_CHECK_HASH']).lower()}",
        f"SCAN_INCREMENTAL={str(config['SCAN_INCREMENTAL']).lower()}",
        "",
        "# ============================================================================",
        "# DECISION SETTINGS",
        "# ============================================================================",
        f"AUTO_APPROVE_THRESHOLD={config['AUTO_APPROVE_THRESHOLD']}",
        f"QUARANTINE_RETENTION_DAYS={config['QUARANTINE_RETENTION_DAYS']}",
        f"PREFER_HIGH_BITRATE={str(config['PREFER_HIGH_BITRATE']).lower()}",
        f"PREFER_HIGH_SAMPLE_RATE={str(config['PREFER_HIGH_SAMPLE_RATE']).lower()}",
        f"PREFER_VALID_INTEGRITY={str(config['PREFER_VALID_INTEGRITY']).lower()}",
        "",
    ])

    path.write_text("\n".join(lines))


def _write_toml_file(config: dict, path: Path) -> None:
    """Write configuration as config.toml file."""
    lines = [
        "# Dedupe Configuration",
        f"# Generated by: dedupe init",
        f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "[db]",
        f'path = "{config["DEDUPE_DB"]}"',
        "min_disk_space_mb = 50",
        "write_sanity_check = true",
        "",
        "[library]",
        f'root = "{config["VOLUME_LIBRARY"]}"',
        "",
        "[volumes]",
    ]

    for key, value in sorted(config.items()):
        if key.startswith("VOLUME_"):
            zone = key.replace("VOLUME_", "").lower()
            lines.append(f'{zone} = "{value}"')

    lines.extend([
        "",
        "[output]",
        f'artifacts = "{config["DEDUPE_ARTIFACTS"]}"',
        f'reports = "{config["DEDUPE_REPORTS"]}"',
        "",
        "[scan]",
        f'workers = {config["SCAN_WORKERS"]}',
        f'progress_interval = {config["SCAN_PROGRESS_INTERVAL"]}',
        f'check_integrity = {str(config["SCAN_CHECK_INTEGRITY"]).lower()}',
        f'check_hash = {str(config["SCAN_CHECK_HASH"]).lower()}',
        f'incremental = {str(config["SCAN_INCREMENTAL"]).lower()}',
        "",
        "[decisions]",
        f'auto_approve_threshold = {config["AUTO_APPROVE_THRESHOLD"]}',
        f'quarantine_retention_days = {config["QUARANTINE_RETENTION_DAYS"]}',
        f'prefer_high_bitrate = {str(config["PREFER_HIGH_BITRATE"]).lower()}',
        f'prefer_high_sample_rate = {str(config["PREFER_HIGH_SAMPLE_RATE"]).lower()}',
        f'prefer_valid_integrity = {str(config["PREFER_VALID_INTEGRITY"]).lower()}',
        "",
    ])

    path.write_text("\n".join(lines))


@cli.command(name="_recover", hidden=True)
@click.argument('path', required=False, type=click.Path(exists=True))
@click.option('--db', type=click.Path(), help='Recovery database path')
@click.option(
    '--phase',
    type=click.Choice(['scan', 'repair', 'verify', 'report', 'all']),
    default='all',
    help='Pipeline phase to run (default: all)'
)
@click.option('--output', type=click.Path(), help='Report output path (CSV or JSON)')
@click.option('--workers', default=4, help='Parallel workers for scan phase')
@click.option('--execute', is_flag=True, help='Actually perform repairs (default: dry-run)')
@click.option('--include-valid', is_flag=True, help='Include valid files in reports')
@click.option('--init', 'interactive', is_flag=True, help='Interactive session initialization')
@click.option('--enrich', is_flag=True, help='Enrich salvaged files with metadata after verification')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def recover(
    path, db, phase, output, workers,
    execute, include_valid, interactive, enrich, verbose
):
    """
    Recover corrupted FLAC files.

    Scans for integrity issues, attempts FFmpeg-based salvage,
    verifies repairs, and generates reports.

    Internal command used by canonical verify/report wrappers.
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
        output = str(config["output"])
        workers = config["workers"]
        execute = True  # Interactive mode implies execution
        phase = 'all'

    # Validate required options
    if not db:
        raise click.ClickException("--db is required (or use --init for interactive setup)")

    db_path = Path(db)

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

        repairer = Repairer(
            db_path,
            dry_run=not execute,
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

        # No backup cleanup in move-only mode

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


@cli.group(name="_metadata", hidden=True)
def metadata():
    """Internal metadata enrichment commands."""


@metadata.command()
@click.option('--db', type=click.Path(), required=False, help='Database path')
@click.option('--path', type=str, help='Filter files by path pattern (SQL LIKE) or file/dir in --standalone mode')
@click.option('--zones', type=str, help='Comma-separated zones to include (e.g. accepted,staging)')
@click.option('--providers', default='beatport,spotify,tidal,qobuz,itunes', help='Comma-separated list of providers (order = priority)')
@click.option('--limit', type=int, help='Maximum files to process')
@click.option('--force', is_flag=True, help='Re-process ALL already-processed files')
@click.option('--retry-no-match', is_flag=True, help='Retry files that had no provider match')
@click.option('--execute', is_flag=True, help='Actually update database (default: dry-run)')
@click.option('--recovery', is_flag=True, help='Recovery mode: focus on duration health validation')
@click.option('--hoarding', is_flag=True, help='Hoarding mode: collect full metadata (BPM, key, genre, etc.)')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.option('--standalone', is_flag=True, help='Run without a database (read tags directly)')
def enrich(db, path, zones, providers, limit, force, retry_no_match, execute, recovery, hoarding, verbose, standalone):
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
        tagslut index enrich --db music.db --recovery --execute

        # Hoarding mode: collect full metadata for DJ library
        tagslut index enrich --db music.db --hoarding --providers beatport,spotify --execute

        # Both modes: health check + full metadata
        tagslut index enrich --db music.db --recovery --hoarding --execute

        # Filter by path pattern
        tagslut index enrich --db music.db --recovery --path "/Volumes/Music/DJ/%" --execute
    """
    from dedupe.metadata.enricher import Enricher
    from dedupe.metadata.auth import TokenManager
    from dedupe.storage.schema import init_db
    import sqlite3
    from datetime import datetime

    if not db and not standalone:
        raise click.ClickException("--db is required (or use --standalone)")
    if db and standalone:
        raise click.ClickException("--standalone cannot be used with --db")

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

    if standalone:
        if not path:
            raise click.ClickException("--path is required in --standalone mode (file or directory)")
        if zones:
            click.echo("Warning: --zones filter is ignored in standalone mode")
        if execute:
            click.echo("Note: --execute is ignored in standalone mode (no DB writes).")
        file_paths = _collect_flac_paths(path)
        if limit:
            file_paths = file_paths[:limit]
        if not file_paths:
            click.echo("No FLAC files found to enrich.")
            return

        # Minimal console logging for standalone runs
        logging.basicConfig(
            level=logging.DEBUG if verbose else logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

        provider_list = [p.strip() for p in providers.split(',') if p.strip()]
        token_manager = TokenManager()

        click.echo("")
        click.echo("┌" + "─" * 50 + "┐")
        if mode == "recovery":
            click.echo("│  METADATA ENRICHMENT - Recovery Mode              │")
        elif mode == "hoarding":
            click.echo("│  METADATA ENRICHMENT - Hoarding Mode              │")
        else:
            click.echo("│  METADATA ENRICHMENT - Recovery + Hoarding        │")
        click.echo("└" + "─" * 50 + "┘")
        click.echo("")
        click.echo(f"  Files:      {len(file_paths)}")
        click.echo(f"  Providers:  {' → '.join(provider_list)}")
        click.echo("")

        stats = {"total": 0, "enriched": 0, "no_match": 0, "failed": 0}

        with Enricher(
            db_path=Path("__standalone__"),
            token_manager=token_manager,
            providers=provider_list,
            dry_run=True,
            mode=mode,
        ) as enricher:
            for i, file_path in enumerate(file_paths, start=1):
                click.echo(f"[{i}/{len(file_paths)}] {file_path}")
                try:
                    file_info = _local_file_info_from_path(file_path)
                    result = enricher.resolve_file(file_info)
                    if result.matches:
                        stats["enriched"] += 1
                    else:
                        stats["no_match"] += 1
                    _print_enrichment_result(result)
                except Exception as e:
                    stats["failed"] += 1
                    click.echo(f"Error: {e}")
                stats["total"] += 1
                click.echo("")

        click.echo(f"{'='*50}")
        click.echo("RESULTS")
        click.echo(f"{'='*50}")
        click.echo(f"  Total:      {stats['total']:>6}")
        click.echo(f"  Enriched:   {stats['enriched']:>6}  ✓")
        click.echo(f"  No match:   {stats['no_match']:>6}")
        click.echo(f"  Failed:     {stats['failed']:>6}")
        return

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
            click.echo("  beatport: Run 'tagslut auth login beatport'")
            click.echo("            (paste token from dj.beatport.com DevTools)")
        if 'tidal' in unconfigured:
            click.echo("  tidal:    Run 'tagslut auth login tidal'")
        if 'qobuz' in unconfigured:
            click.echo("  qobuz:    Run 'tagslut auth login qobuz'")


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
    click.echo("  2. Tidal: Run 'tagslut auth login tidal'")
    click.echo("  3. Qobuz: Run 'tagslut auth login qobuz'")
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
            click.echo("Run 'tagslut auth login beatport' to set a new token.")

    elif provider == 'tidal':
        click.echo("Refreshing Tidal token...")
        token = token_manager.refresh_tidal_token()
        if token:
            click.echo(f"Success! Token expires at: {time.ctime(token.expires_at)}")
        else:
            click.echo("Failed. Run 'tagslut auth login tidal' first.")

    elif provider == 'qobuz':
        click.echo("Qobuz tokens don't expire. Run 'tagslut auth login qobuz' to re-authenticate.")

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


@cli.group(name="_mgmt", invoke_without_command=True, hidden=True)
@click.option("--m3u", "m3u_mode", is_flag=True, help="Generate Roon-compatible M3U playlist(s)")
@click.option("--merge", is_flag=True, help="Merge all items into a single M3U")
@click.option("--m3u-dir", type=click.Path(), help="Output directory for M3U files")
@click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
@click.option("--source", help="Source label for playlist naming (bpdl, tidal, etc.)")
@click.option("--path", "paths", multiple=True, type=click.Path(), help="Input path(s) for --m3u")
@click.pass_context
def mgmt(ctx, m3u_mode, merge, m3u_dir, db, source, paths):
    """Internal management mode: inventory tracking and duplicate checking."""
    if ctx.invoked_subcommand is None:
        if not m3u_mode:
            click.echo(ctx.get_help())
            return
        if not paths:
            raise click.ClickException("Provide at least one PATH when using --m3u")

        from dedupe.storage.schema import get_connection, init_db
        from dedupe.utils.db import resolve_db_path
        from dedupe.utils.config import get_config
        from datetime import datetime, timezone

        config = get_config()
        default_m3u_dir = config.get("mgmt.m3u_dir") if config else None
        output_dir = Path(m3u_dir) if m3u_dir else (Path(default_m3u_dir).expanduser() if default_m3u_dir else None)

        input_paths = [Path(p).expanduser().resolve() for p in paths]
        flac_files = _collect_flac_inputs(tuple(paths))
        if not flac_files:
            raise click.ClickException("No FLAC files found in provided PATHS")

        if output_dir is None:
            if len(input_paths) == 1 and input_paths[0].is_dir():
                output_dir = input_paths[0]
            else:
                output_dir = Path.cwd()

        groups: dict[str, list[Path]] = {}
        if merge:
            groups["merged"] = sorted(flac_files, key=lambda p: str(p))
        else:
            base_paths = [p for p in input_paths if p.exists()]
            for file_path in flac_files:
                group = _resolve_group_name(file_path, base_paths)
                groups.setdefault(group, []).append(file_path)
            for group_name in list(groups.keys()):
                groups[group_name] = sorted(groups[group_name], key=lambda p: str(p))

        resolution = resolve_db_path(db, purpose="write", allow_create=True)
        conn = get_connection(str(resolution.path), purpose="write", allow_create=True)
        init_db(conn)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(files)")}
        has_m3u_path = "m3u_path" in columns

        now_iso = datetime.now(timezone.utc).isoformat()
        playlist_outputs: list[Path] = []
        try:
            for group_name, files in groups.items():
                playlist_name = _safe_playlist_name(group_name)
                if merge:
                    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    label = source or "dedupe"
                    playlist_name = f"{label}-{stamp}"

                output_path = _write_m3u(
                    playlist_name=playlist_name,
                    files=files,
                    output_dir=output_dir,
                )
                playlist_outputs.append(output_path)

                for file_path in files:
                    if has_m3u_path:
                        conn.execute(
                            "UPDATE files SET m3u_exported = ?, m3u_path = ? WHERE path = ?",
                            (now_iso, str(output_path), str(file_path)),
                        )
                    else:
                        conn.execute(
                            "UPDATE files SET m3u_exported = ? WHERE path = ?",
                            (now_iso, str(file_path)),
                        )
            conn.commit()
        finally:
            conn.close()

        click.echo(f"Generated {len(playlist_outputs)} M3U file(s):")
        for item in playlist_outputs:
            click.echo(f"  {item}")

def _duration_thresholds_from_config() -> tuple[int, int]:
    from dedupe.utils.config import get_config

    config = get_config()
    ok_max = int(config.get("mgmt.duration.ok_max_delta_ms", 2000) or 2000)
    warn_max = int(config.get("mgmt.duration.warn_max_delta_ms", 8000) or 8000)
    return ok_max, warn_max


def _duration_check_version(ok_max_ms: int, warn_max_ms: int) -> str:
    return f"duration_v1_ok{ok_max_ms//1000}_warn{warn_max_ms//1000}"


def _duration_status(delta_ms: int | None, ok_max_ms: int, warn_max_ms: int) -> str:
    if delta_ms is None:
        return "unknown"
    abs_delta = abs(delta_ms)
    if abs_delta <= ok_max_ms:
        return "ok"
    if abs_delta <= warn_max_ms:
        return "warn"
    return "fail"


def _collect_flac_inputs(paths: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for input_path in paths:
        files.extend(_collect_flac_paths(input_path))
    return files


def _resolve_group_name(file_path: Path, base_paths: list[Path]) -> str:
    best_base: Path | None = None
    best_parts = -1
    for base in base_paths:
        try:
            rel = file_path.relative_to(base)
        except ValueError:
            continue
        if len(rel.parts) > best_parts:
            best_parts = len(rel.parts)
            best_base = base

    if best_base is None:
        return file_path.parent.name or "playlist"

    rel = file_path.relative_to(best_base)
    if len(rel.parts) > 1:
        return rel.parts[0]
    return best_base.name or file_path.parent.name or "playlist"


def _safe_playlist_name(name: str) -> str:
    cleaned = name.strip().replace("/", "-").replace("\\", "-")
    return cleaned or "playlist"


def _format_extinf(file_path: Path) -> tuple[int, str]:
    try:
        from mutagen.flac import FLAC
        audio = FLAC(file_path)
        duration = int(audio.info.length) if audio.info.length else -1
        tags = audio.tags or {}
        artist = _extract_tag_value(tags, ["artist", "albumartist"]) or "Unknown"
        title = _extract_tag_value(tags, ["title"]) or file_path.stem
        return duration, f"{artist} - {title}"
    except Exception:
        return -1, file_path.stem


def _write_m3u(
    *,
    playlist_name: str,
    files: list[Path],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_playlist_name(playlist_name)
    output_path = output_dir / f"{safe_name}.m3u"

    lines = ["#EXTM3U", "#EXTENC: UTF-8", f"#PLAYLIST:{playlist_name}"]
    for file_path in files:
        duration, label = _format_extinf(file_path)
        lines.append(f"#EXTINF:{duration},{label}")
        lines.append(str(file_path.resolve()))

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _prompt_duplicate_action(
    *,
    file_path: Path,
    matches: list[tuple[str, str | None]],
    prompt_enabled: bool,
) -> str:
    if not prompt_enabled or not sys.stdin.isatty():
        return "skip"

    click.echo("\n⚠️  Similar track found in inventory:")
    click.echo(f"\nEXISTING for {file_path.name}:")
    for match_path, match_source in matches[:5]:
        src = match_source or "unknown"
        click.echo(f"  → {src}: {match_path}")
    if len(matches) > 5:
        click.echo(f"  ... and {len(matches) - 5} more")

    click.echo("\nActions: [S]kip  [D]ownload anyway  [R]eplace  [Q]uit")
    choice = click.prompt("Choose action", default="S", show_default=True)
    choice = choice.strip().lower()
    if choice in {"s", "skip"}:
        return "skip"
    if choice in {"d", "download", "download anyway", "download_anyway"}:
        return "download"
    if choice in {"r", "replace"}:
        return "replace"
    if choice in {"q", "quit"}:
        return "quit"
    return "skip"


def _measure_duration_ms(file_path: Path) -> int | None:
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(str(file_path), easy=False)
        if audio is None or not hasattr(audio, "info") or audio.info is None:
            return None
        length = getattr(audio.info, "length", None)
        if length is None:
            return None
        return int(round(float(length) * 1000))
    except Exception:
        return None


def _extract_tag_value(tags: dict, keys: list[str]) -> str | None:
    if not tags:
        return None
    lowered = {str(k).lower(): v for k, v in tags.items()}
    for key in keys:
        raw = lowered.get(key.lower())
        if raw is None:
            continue
        if isinstance(raw, (list, tuple)):
            if not raw:
                continue
            return str(raw[0]).strip() or None
        return str(raw).strip() or None
    return None


def _lookup_duration_ref_ms(
    conn,
    beatport_id: str | None,
    isrc: str | None,
) -> tuple[int | None, str | None, str | None]:
    if beatport_id:
        row = conn.execute(
            "SELECT duration_ref_ms, ref_source FROM track_duration_refs WHERE ref_id = ?",
            (beatport_id,),
        ).fetchone()
        if row:
            return int(row[0]), row[1], beatport_id
        row = conn.execute(
            """
            SELECT canonical_duration, canonical_duration_source
            FROM files
            WHERE beatport_id = ? AND canonical_duration IS NOT NULL
            LIMIT 1
            """,
            (beatport_id,),
        ).fetchone()
        if row and row[0] is not None:
            return int(round(float(row[0]) * 1000)), row[1], beatport_id
    if isrc:
        row = conn.execute(
            "SELECT duration_ref_ms, ref_source FROM track_duration_refs WHERE ref_id = ?",
            (isrc,),
        ).fetchone()
        if row:
            return int(row[0]), row[1], isrc
        row = conn.execute(
            """
            SELECT canonical_duration, canonical_duration_source
            FROM files
            WHERE canonical_isrc = ? AND canonical_duration IS NOT NULL
            LIMIT 1
            """,
            (isrc,),
        ).fetchone()
        if row and row[0] is not None:
            return int(round(float(row[0]) * 1000)), row[1], isrc
    return None, None, None


@mgmt.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--source', required=True, help='Download source (bpdl, tidal, qobuz, legacy, etc.)')
@click.option('--db', type=click.Path(), help='Database path (auto-detect from env if not provided)')
@click.option('--execute', is_flag=True, help='Actually register files (default: dry-run)')
@click.option(
    '--full-hash',
    is_flag=True,
    help='Compute full-file SHA256 for every file (slow; default uses FLAC STREAMINFO MD5 when available)',
)
@click.option('--limit', type=int, help='Only process first N files (useful for smoke tests)')
@click.option('--dj-only', is_flag=True, help='Mark all registered files as DJ material')
@click.option('--check-duration', is_flag=True, help='Measure duration and compute duration status')
@click.option('--prompt/--no-prompt', default=True, help='Prompt when similar files exist')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def register(path, source, db, execute, full_hash, limit, dj_only, check_duration, prompt, verbose):
    """
    Register files in inventory.

    Scans directory for FLAC files, computes checksums, and registers
    them in the database with source tracking. Used after downloading
    from Beatport, Tidal, Qobuz, etc.

    \b
    Examples:
        # Dry-run: see what would be registered
        tagslut index register ~/Downloads/bpdl --source bpdl

        # Actually register
        tagslut index register ~/Downloads/bpdl --source bpdl --execute

        # Verbose output
        tagslut index register ~/Downloads/bpdl --source bpdl --execute -v

        # Register with duration checks for DJ material
        tagslut index register ~/Downloads/bpdl --source bpdl --dj-only --check-duration --execute
    """
    from dedupe.storage.schema import get_connection, init_db
    from dedupe.storage.queries import get_file
    from dedupe.storage.v3 import dual_write_enabled, dual_write_registered_file
    from dedupe.core.hashing import calculate_file_hash
    from dedupe.core.metadata import extract_metadata
    from dedupe.utils.db import resolve_db_path
    from datetime import datetime, timezone
    from dedupe.utils.audit_log import append_jsonl, resolve_log_path
    from dedupe.utils.config import get_config
    from dedupe.utils.paths import list_files
    from dedupe.utils.zones import get_default_zone_manager
    import json
    import itertools

    resolution = resolve_db_path(
        db,
        purpose="write" if execute else "read",
        allow_create=bool(execute),
    )
    db_path = resolution.path

    path_obj = Path(path).expanduser().resolve()
    if not path_obj.exists():
        raise click.ClickException(f"Path not found: {path}")

    # Collect FLAC files (streaming; avoids huge in-memory lists for big libraries).
    flac_iter = list_files(path_obj, {".flac"})
    if limit:
        flac_iter = itertools.islice(flac_iter, int(limit))

    click.echo(f"Scanning: {path_obj}")
    click.echo(f"Source: {source}")
    click.echo(f"Hashing: {'full sha256' if full_hash else 'streaminfo md5 (sha256 fallback)'}")
    if limit:
        click.echo(f"Limit: {limit}")
    if not execute:
        click.echo("[DRY-RUN MODE - use --execute to save]")
    click.echo("")

    config = get_config()
    log_dir = None
    if config:
        configured_dir = config.get("mgmt.audit_log_dir")
        if configured_dir:
            log_dir = Path(configured_dir).expanduser()

    conn = get_connection(str(db_path), purpose="write" if execute else "read", allow_create=bool(execute))
    if execute:
        init_db(conn)
    try:
        dual_write_v3 = bool(execute and dual_write_enabled())
        if dual_write_v3:
            click.echo("V3 dual-write: enabled")
        registered = 0
        skipped = 0
        errors = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        ok_max_ms, warn_max_ms = _duration_thresholds_from_config()
        duration_version = _duration_check_version(ok_max_ms, warn_max_ms)
        zone_manager = get_default_zone_manager()

        total = 0
        for i, file_path in enumerate(flac_iter, start=1):
            total = i
            try:
                mgmt_status_override = None

                # Check if already registered
                existing = get_file(conn, file_path)
                if existing:
                    if verbose:
                        click.echo(f"  [{i}] SKIP (already registered) {file_path.name}")
                    skipped += 1
                    continue

                # Extract STREAMINFO MD5 + tags/tech. Full hash is optional for speed.
                audio = extract_metadata(
                    file_path,
                    scan_integrity=False,
                    scan_hash=bool(full_hash),
                    library="default",
                    zone_manager=zone_manager,
                )

                checksum = audio.checksum
                sha256 = audio.sha256
                streaminfo_md5 = audio.streaminfo_md5
                if (not streaminfo_md5) and (not sha256):
                    sha256 = calculate_file_hash(file_path)
                    checksum = sha256

                zone_value = audio.zone.value if audio.zone else "suspect"
                metadata_json = json.dumps(audio.metadata or {}, ensure_ascii=False, sort_keys=True)

                # Check for existing file with same content fingerprint
                if sha256:
                    existing_matches = conn.execute(
                        "SELECT path, download_source FROM files WHERE sha256 = ? OR checksum = ?",
                        (sha256, sha256),
                    ).fetchall()
                    content_id_for_log = sha256
                    content_id_type = "sha256"
                elif streaminfo_md5:
                    stream_checksum = f"streaminfo:{streaminfo_md5}"
                    existing_matches = conn.execute(
                        "SELECT path, download_source FROM files WHERE streaminfo_md5 = ? OR checksum = ?",
                        (streaminfo_md5, stream_checksum),
                    ).fetchall()
                    content_id_for_log = streaminfo_md5
                    content_id_type = "streaminfo_md5"
                else:
                    existing_matches = []
                    content_id_for_log = None
                    content_id_type = "none"

                if existing_matches:
                    action = _prompt_duplicate_action(
                        file_path=file_path,
                        matches=existing_matches,
                        prompt_enabled=prompt,
                    )
                    append_jsonl(
                        resolve_log_path("mgmt_decisions", default_dir=log_dir),
                        {
                            "event": "duplicate_decision",
                            "timestamp": now_iso,
                            "path": str(file_path),
                            "content_id": content_id_for_log,
                            "content_id_type": content_id_type,
                            "source": source,
                            "action": action,
                            "matches": [
                                {"path": match[0], "source": match[1]}
                                for match in existing_matches[:10]
                            ],
                        },
                    )
                    if action == "quit":
                        raise click.ClickException("User aborted")
                    if action == "skip":
                        if verbose:
                            click.echo(f"  [{i}] SKIP (duplicate) {file_path.name}")
                        skipped += 1
                        continue
                    if action == "replace":
                        if verbose:
                            click.echo(f"  [{i}] REPLACE (marked) {file_path.name}")
                        mgmt_status_override = "needs_review"

                duration_measured_ms = None
                duration_ref_ms = None
                duration_ref_source = None
                duration_ref_track_id = None
                duration_delta_ms = None
                duration_status = None
                duration_measured_at = None
                duration_ref_updated_at = None

                if check_duration:
                    duration_measured_ms = _measure_duration_ms(file_path)
                    duration_measured_at = now_iso

                    beatport_id = _extract_tag_value(audio.metadata, ["BEATPORT_TRACK_ID", "BP_TRACK_ID", "beatport_track_id"])
                    isrc = _extract_tag_value(audio.metadata, ["ISRC", "TSRC"])

                    duration_ref_ms, duration_ref_source, duration_ref_track_id = _lookup_duration_ref_ms(
                        conn, beatport_id, isrc
                    )
                    if duration_ref_ms is not None:
                        duration_ref_updated_at = now_iso
                    if duration_measured_ms is not None and duration_ref_ms is not None:
                        duration_delta_ms = duration_measured_ms - duration_ref_ms
                    duration_status = _duration_status(duration_delta_ms, ok_max_ms, warn_max_ms)

                    log_payload = {
                        "event": "duration_check",
                        "timestamp": now_iso,
                        "path": str(file_path),
                        "source": source,
                        "track_id": f"beatport:{beatport_id}" if beatport_id else (f"isrc:{isrc}" if isrc else None),
                        "is_dj_material": bool(dj_only),
                        "duration_ref_ms": duration_ref_ms,
                        "duration_measured_ms": duration_measured_ms,
                        "duration_delta_ms": duration_delta_ms,
                        "duration_status": duration_status,
                        "thresholds_ms": {"ok": ok_max_ms, "warn": warn_max_ms},
                        "check_version": duration_version,
                    }
                    append_jsonl(resolve_log_path("mgmt_duration"), log_payload)

                    if dj_only and duration_status in ("warn", "fail", "unknown"):
                        anomaly_payload = {
                            "event": "duration_anomaly",
                            "timestamp": now_iso,
                            "path": str(file_path),
                            "track_id": log_payload["track_id"],
                            "is_dj_material": True,
                            "duration_status": duration_status,
                            "duration_ref_ms": duration_ref_ms,
                            "duration_measured_ms": duration_measured_ms,
                            "duration_delta_ms": duration_delta_ms,
                            "action": "blocked_promotion",
                        }
                        append_jsonl(resolve_log_path("mgmt_duration"), anomaly_payload)
                        mgmt_status_override = mgmt_status_override or "needs_review"

                # Register in database
                if execute:
                    flac_ok_value = None if audio.flac_ok is None else int(bool(audio.flac_ok))
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO files (
                            path, checksum, streaminfo_md5, sha256, library, zone, mtime, size,
                            duration, bit_depth, sample_rate, bitrate, metadata_json, flac_ok, integrity_state,
                            download_source, download_date, original_path, mgmt_status,
                            is_dj_material, duration_ref_ms, duration_ref_source, duration_ref_track_id,
                            duration_ref_updated_at, duration_measured_ms, duration_measured_at,
                            duration_delta_ms, duration_status, duration_check_version
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(file_path),
                            checksum,
                            streaminfo_md5,
                            sha256,
                            "default",
                            zone_value,
                            audio.mtime,
                            audio.size,
                            float(audio.duration or 0.0),
                            int(audio.bit_depth or 0),
                            int(audio.sample_rate or 0),
                            int(audio.bitrate or 0),
                            metadata_json,
                            flac_ok_value,
                            audio.integrity_state,
                            source,
                            now_iso,
                            str(file_path),  # original_path = current path (no move yet)
                            mgmt_status_override
                            or (
                                "needs_review"
                                if dj_only and duration_status in ("warn", "fail", "unknown")
                                else "new"
                            ),
                            1 if dj_only else 0,
                            duration_ref_ms,
                            duration_ref_source,
                            duration_ref_track_id,
                            duration_ref_updated_at,
                            duration_measured_ms,
                            duration_measured_at,
                            duration_delta_ms,
                            duration_status,
                            duration_version if check_duration else None,
                        ),
                    )
                    if dual_write_v3:
                        dual_write_registered_file(
                            conn,
                            path=str(file_path),
                            content_sha256=sha256,
                            streaminfo_md5=streaminfo_md5,
                            checksum=checksum,
                            size_bytes=audio.size,
                            mtime=audio.mtime,
                            duration_s=float(audio.duration or 0.0),
                            sample_rate=int(audio.sample_rate or 0),
                            bit_depth=int(audio.bit_depth or 0),
                            bitrate=int(audio.bitrate or 0),
                            library="default",
                            zone=zone_value,
                            download_source=source,
                            download_date=now_iso,
                            mgmt_status=mgmt_status_override
                            or (
                                "needs_review"
                                if dj_only and duration_status in ("warn", "fail", "unknown")
                                else "new"
                            ),
                            metadata=audio.metadata or {},
                            duration_ref_ms=duration_ref_ms,
                            duration_ref_source=duration_ref_source,
                            event_time=now_iso,
                        )

                if verbose or i % 50 == 0:
                    click.echo(f"  [{i}] {file_path.name}")

                registered += 1

            except Exception as e:
                errors += 1
                click.echo(f"  ERROR: {file_path.name}: {e}")

        if total == 0:
            click.echo(f"No FLAC files found in {path}")
            return

        if execute:
            conn.commit()

    finally:
        conn.close()

    click.echo("")
    click.echo(f"{'='*50}")
    click.echo("RESULTS")
    click.echo(f"{'='*50}")
    click.echo(f"  Total:       {total:>6}")
    click.echo(f"  Registered:  {registered:>6}  {'✓' if registered > 0 else '(none)'}")
    click.echo(f"  Skipped:     {skipped:>6}  (already registered)")
    click.echo(f"  Errors:      {errors:>6}  {'⚠' if errors > 0 else ''}")


@mgmt.command()
@click.argument('path', type=click.Path(exists=True), required=False)
@click.option('--source', help='Filter by download source')
@click.option('--db', type=click.Path(), help='Database path (auto-detect from env if not provided)')
@click.option('--strict', is_flag=True, help='Strict mode: any match is a conflict')
@click.option('--prompt/--no-prompt', default=True, help='Prompt when similar files exist')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def check(path, source, db, strict, prompt, verbose):
    """
    Check for duplicate files before downloading.

    Scans a directory (or stdin) and checks if any files already
    exist in the database. Useful to avoid re-downloading known files.

    If no path is provided, reads file paths from stdin (one per line).

    \b
    Examples:
        # Check a directory
        tagslut index check ~/Downloads/bpdl --source bpdl

        # Check with pipe
        find ~/incoming -name "*.flac" | tagslut index check --source tidal

        # Strict mode: reject if SAME file exists anywhere
        tagslut index check ~/Downloads --strict
    """
    from dedupe.storage.schema import get_connection
    from dedupe.core.hashing import calculate_file_hash
    from dedupe.utils.db import resolve_db_path
    from dedupe.utils.audit_log import append_jsonl, resolve_log_path
    from dedupe.utils.config import get_config
    from datetime import datetime, timezone
    import sys

    # Resolve database path (auto-detect from CLI/env/config)
    resolution = resolve_db_path(db, purpose="read")
    db_path = resolution.path

    # Collect file paths from argument or stdin
    file_paths = []
    if path:
        path_obj = Path(path).expanduser().resolve()
        if path_obj.is_file():
            file_paths = [path_obj]
        elif path_obj.is_dir():
            file_paths = list(path_obj.rglob("*.flac"))
        else:
            raise click.ClickException(f"Path not found: {path}")
    else:
        # Read from stdin
        for line in sys.stdin:
            file_path = Path(line.strip()).expanduser().resolve()
            if file_path.exists() and file_path.suffix.lower() == ".flac":
                file_paths.append(file_path)

    if not file_paths:
        click.echo("No FLAC files provided")
        return

    click.echo(f"Checking {len(file_paths)} files against database...")
    if source:
        click.echo(f"Filter: source={source}")
    if strict:
        click.echo("Mode: STRICT (any match is a conflict)")
    click.echo("")

    config = get_config()
    log_dir = None
    if config:
        configured_dir = config.get("mgmt.audit_log_dir")
        if configured_dir:
            log_dir = Path(configured_dir).expanduser()

    conn = get_connection(str(db_path), purpose="read")
    try:
        duplicates = []
        unique = []
        allowed = []
        replacements = []
        errors = 0

        for i, file_path in enumerate(file_paths, start=1):
            try:
                # Compute checksum
                sha256 = calculate_file_hash(file_path)

                # Query database directly to check for existing file with same sha256
                if strict:
                    # Any match is a conflict
                    cursor = conn.execute(
                        "SELECT path, download_source FROM files WHERE sha256 = ?",
                        (sha256,)
                    )
                else:
                    # Only match if same source
                    if source:
                        cursor = conn.execute(
                            "SELECT path, download_source FROM files WHERE sha256 = ? AND download_source = ?",
                            (sha256, source)
                        )
                    else:
                        cursor = conn.execute(
                            "SELECT path, download_source FROM files WHERE sha256 = ?",
                            (sha256,)
                        )

                existing = cursor.fetchall()

                if existing:
                    action = _prompt_duplicate_action(
                        file_path=file_path,
                        matches=existing,
                        prompt_enabled=prompt,
                    )
                    append_jsonl(
                        resolve_log_path("mgmt_checks", default_dir=log_dir),
                        {
                            "event": "duplicate_check",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "path": str(file_path),
                            "sha256": sha256,
                            "source_filter": source,
                            "strict": bool(strict),
                            "action": action,
                            "matches": [
                                {"path": match[0], "source": match[1]}
                                for match in existing[:10]
                            ],
                        },
                    )
                    if action == "quit":
                        raise click.ClickException("User aborted")
                    if action == "download":
                        allowed.append(file_path)
                        if verbose:
                            click.echo(f"  ALLOW: {file_path.name}")
                    elif action == "replace":
                        replacements.append((file_path, existing))
                        if verbose:
                            click.echo(f"  REPLACE: {file_path.name}")
                    else:
                        duplicates.append((file_path, existing))
                        if verbose:
                            click.echo(f"  CONFLICT: {file_path.name}")
                            for match in existing:
                                src = match[1] if match[1] else "unknown"
                                click.echo(f"    → {src}: {Path(match[0]).name}")
                else:
                    unique.append(file_path)
                    if verbose:
                        click.echo(f"  OK: {file_path.name}")

                if i % 50 == 0 or i == len(file_paths):
                    click.echo(f"  [{i}/{len(file_paths)}]...")

            except Exception as e:
                errors += 1
                click.echo(f"  ERROR: {file_path.name}: {e}")

    finally:
        conn.close()

    click.echo("")
    click.echo(f"{'='*50}")
    click.echo("RESULTS")
    click.echo(f"{'='*50}")
    click.echo(f"  Total:        {len(file_paths):>6}")
    click.echo(f"  Unique:       {len(unique):>6}  ✓ (safe to download)")
    click.echo(f"  Allowed:      {len(allowed):>6}  ✓ (download anyway)")
    click.echo(f"  Replace:      {len(replacements):>6}  ⚠ (mark for replace)")
    click.echo(f"  Duplicates:   {len(duplicates):>6}  ⚠ (already exists)")
    click.echo(f"  Errors:       {errors:>6}  {'⚠' if errors > 0 else ''}")

    if duplicates:
        click.echo("")
        click.echo("Conflicts (files that already exist):")
        for file_path, matches in duplicates[:10]:
            click.echo(f"  • {file_path.name}")
            for match in matches[:2]:
                src = match[1] if match[1] else "unknown"
                click.echo(f"    → {src}: {Path(match[0]).name}")
            if len(matches) > 2:
                click.echo(f"    ... and {len(matches) - 2} more")
        if len(duplicates) > 10:
            click.echo(f"  ... and {len(duplicates) - 10} more conflicts")

    if replacements:
        click.echo("")
        click.echo("Replace candidates:")
        for file_path, matches in replacements[:10]:
            click.echo(f"  • {file_path.name}")
            for match in matches[:2]:
                src = match[1] if match[1] else "unknown"
                click.echo(f"    → {src}: {Path(match[0]).name}")
            if len(matches) > 2:
                click.echo(f"    ... and {len(matches) - 2} more")
        if len(replacements) > 10:
            click.echo(f"  ... and {len(replacements) - 10} more replacements")


@mgmt.command("check-duration")
@click.argument("path", type=click.Path(exists=True))
@click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
@click.option("--execute", is_flag=True, help="Write duration updates to the database")
@click.option("--dj-only", is_flag=True, help="Mark checked files as DJ material")
@click.option("--source", help="Override source label for logging")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
def check_duration(path, db, execute, dj_only, source, verbose):
    """
    Measure durations and update duration status in the DB.
    """
    from dedupe.storage.schema import get_connection, init_db
    from dedupe.utils.db import resolve_db_path
    from dedupe.utils.audit_log import append_jsonl, resolve_log_path
    from mutagen.flac import FLAC
    from datetime import datetime, timezone

    resolution = resolve_db_path(
        db,
        purpose="write" if execute else "read",
        allow_create=bool(execute),
    )
    db_path = resolution.path

    path_obj = Path(path).expanduser().resolve()
    if not path_obj.exists():
        raise click.ClickException(f"Path not found: {path}")

    if path_obj.is_file():
        file_paths = [path_obj]
    else:
        file_paths = list(path_obj.rglob("*.flac"))

    if not file_paths:
        click.echo("No FLAC files found to check")
        return

    ok_max_ms, warn_max_ms = _duration_thresholds_from_config()
    duration_version = _duration_check_version(ok_max_ms, warn_max_ms)
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_connection(str(db_path), purpose="write" if execute else "read", allow_create=bool(execute))
    if execute:
        init_db(conn)
    try:
        updated = 0
        missing = 0
        errors = 0

        for i, file_path in enumerate(file_paths, start=1):
            try:
                row = conn.execute("SELECT path FROM files WHERE path = ?", (str(file_path),)).fetchone()
                if not row:
                    missing += 1
                    if verbose:
                        click.echo(f"  [{i}/{len(file_paths)}] SKIP (not in DB) {file_path.name}")
                    continue

                audio = None
                try:
                    audio = FLAC(file_path)
                except Exception:
                    audio = None

                tags = audio.tags or {} if audio is not None else {}
                beatport_id = _extract_tag_value(tags, ["BEATPORT_TRACK_ID", "BP_TRACK_ID", "beatport_track_id"])
                isrc = _extract_tag_value(tags, ["ISRC", "TSRC"])

                duration_ref_ms, duration_ref_source, duration_ref_track_id = _lookup_duration_ref_ms(
                    conn, beatport_id, isrc
                )
                duration_measured_ms = _measure_duration_ms(file_path)
                duration_delta_ms = None
                if duration_measured_ms is not None and duration_ref_ms is not None:
                    duration_delta_ms = duration_measured_ms - duration_ref_ms
                duration_status = _duration_status(duration_delta_ms, ok_max_ms, warn_max_ms)

                log_payload = {
                    "event": "duration_check",
                    "timestamp": now_iso,
                    "path": str(file_path),
                    "source": source,
                    "track_id": f"beatport:{beatport_id}" if beatport_id else (f"isrc:{isrc}" if isrc else None),
                    "is_dj_material": bool(dj_only),
                    "duration_ref_ms": duration_ref_ms,
                    "duration_measured_ms": duration_measured_ms,
                    "duration_delta_ms": duration_delta_ms,
                    "duration_status": duration_status,
                    "thresholds_ms": {"ok": ok_max_ms, "warn": warn_max_ms},
                    "check_version": duration_version,
                }
                append_jsonl(resolve_log_path("mgmt_duration"), log_payload)

                if dj_only and duration_status in ("warn", "fail", "unknown"):
                    anomaly_payload = {
                        "event": "duration_anomaly",
                        "timestamp": now_iso,
                        "path": str(file_path),
                        "track_id": log_payload["track_id"],
                        "is_dj_material": True,
                        "duration_status": duration_status,
                        "duration_ref_ms": duration_ref_ms,
                        "duration_measured_ms": duration_measured_ms,
                        "duration_delta_ms": duration_delta_ms,
                        "action": "blocked_promotion",
                    }
                    append_jsonl(resolve_log_path("mgmt_duration"), anomaly_payload)

                if execute:
                    conn.execute(
                        """
                        UPDATE files SET
                            is_dj_material = CASE WHEN ? THEN 1 ELSE is_dj_material END,
                            duration_ref_ms = ?,
                            duration_ref_source = ?,
                            duration_ref_track_id = ?,
                            duration_ref_updated_at = ?,
                            duration_measured_ms = ?,
                            duration_measured_at = ?,
                            duration_delta_ms = ?,
                            duration_status = ?,
                            duration_check_version = ?,
                            mgmt_status = CASE
                                WHEN ? AND ? IN ('warn','fail','unknown') THEN 'needs_review'
                                ELSE mgmt_status
                            END
                        WHERE path = ?
                        """,
                        (
                            1 if dj_only else 0,
                            duration_ref_ms,
                            duration_ref_source,
                            duration_ref_track_id,
                            now_iso if duration_ref_ms is not None else None,
                            duration_measured_ms,
                            now_iso if duration_measured_ms is not None else None,
                            duration_delta_ms,
                            duration_status,
                            duration_version,
                            1 if dj_only else 0,
                            duration_status,
                            str(file_path),
                        ),
                    )

                if verbose or i % 50 == 0 or i == len(file_paths):
                    click.echo(f"  [{i}/{len(file_paths)}] {file_path.name}")
                updated += 1

            except Exception as e:
                errors += 1
                click.echo(f"  ERROR: {file_path.name}: {e}")

        if execute:
            conn.commit()

    finally:
        conn.close()

    click.echo("")
    click.echo(f"{'='*50}")
    click.echo("DURATION CHECK RESULTS")
    click.echo(f"{'='*50}")
    click.echo(f"  Total:        {len(file_paths):>6}")
    click.echo(f"  Updated:      {updated:>6}")
    click.echo(f"  Missing DB:   {missing:>6}")
    click.echo(f"  Errors:       {errors:>6}  {'⚠' if errors > 0 else ''}")


@mgmt.command("audit-duration")
@click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
@click.option("--dj-only", is_flag=True, help="Only DJ material")
@click.option("--status", "status_filter", help="Comma-separated statuses (warn,fail,unknown)")
@click.option("--source", help="Filter by download source")
@click.option("--since", help="Filter by download_date >= YYYY-MM-DD")
def audit_duration(db, dj_only, status_filter, source, since):
    """
    Report files with duration_status != ok (or filtered statuses).
    """
    from dedupe.storage.schema import get_connection
    from dedupe.utils.db import resolve_db_path

    resolution = resolve_db_path(db, purpose="read")
    db_path = resolution.path

    statuses = None
    if status_filter:
        statuses = [s.strip() for s in status_filter.split(",") if s.strip()]

    conn = get_connection(str(db_path), purpose="read")
    try:
        where = ["1=1"]
        params = []
        if dj_only:
            where.append("is_dj_material = 1")
        if source:
            where.append("download_source = ?")
            params.append(source)
        if since:
            where.append("download_date >= ?")
            params.append(since)
        if statuses:
            where.append(f"duration_status IN ({','.join(['?'] * len(statuses))})")
            params.extend(statuses)
        else:
            where.append("(duration_status IS NULL OR duration_status != 'ok')")

        query = (
            "SELECT path, duration_status, duration_ref_ms, duration_measured_ms, "
            "duration_delta_ms, download_source FROM files WHERE "
            + " AND ".join(where)
            + " ORDER BY download_source, path"
        )

        rows = conn.execute(query, tuple(params)).fetchall()
        click.echo(f"Found {len(rows)} file(s) with duration issues.")
        for row in rows:
            click.echo(
                f"  {row[0]} | status={row[1]} | delta_ms={row[4]} | source={row[5]}"
            )
    finally:
        conn.close()


@mgmt.command("set-duration-ref")
@click.argument("path", type=click.Path(exists=True))
@click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
@click.option("--dj-only", is_flag=True, help="Mark file as DJ material")
@click.option("--confirm", is_flag=True, help="Confirm manual duration reference override")
@click.option("--execute", is_flag=True, help="Write updates to the database")
def set_duration_ref(path, db, dj_only, confirm, execute):
    """
    Manually set a duration reference from a known-good file.
    """
    from dedupe.storage.schema import get_connection, init_db
    from dedupe.utils.db import resolve_db_path
    from dedupe.core.hashing import calculate_file_hash
    from dedupe.utils.audit_log import append_jsonl, resolve_log_path
    from datetime import datetime, timezone

    if execute and not confirm:
        raise click.ClickException("--confirm is required with --execute")

    resolution = resolve_db_path(
        db,
        purpose="write" if execute else "read",
        allow_create=bool(execute),
    )
    db_path = resolution.path

    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise click.ClickException(f"Path not found: {path}")

    duration_measured_ms = _measure_duration_ms(file_path)
    if duration_measured_ms is None:
        raise click.ClickException("Could not measure duration from file")

    sha256 = calculate_file_hash(file_path)
    manual_id = f"manual:{sha256}"
    now_iso = datetime.now(timezone.utc).isoformat()

    ok_max_ms, warn_max_ms = _duration_thresholds_from_config()
    duration_version = _duration_check_version(ok_max_ms, warn_max_ms)

    conn = get_connection(str(db_path), purpose="write" if execute else "read", allow_create=bool(execute))
    if execute:
        init_db(conn)
    try:
        if execute:
            conn.execute(
                """
                INSERT OR REPLACE INTO track_duration_refs
                    (ref_id, ref_type, duration_ref_ms, ref_source, ref_updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (manual_id, "manual", duration_measured_ms, "manual", now_iso),
            )

            conn.execute(
                """
                UPDATE files SET
                    is_dj_material = CASE WHEN ? THEN 1 ELSE is_dj_material END,
                    duration_ref_ms = ?,
                    duration_ref_source = ?,
                    duration_ref_track_id = ?,
                    duration_ref_updated_at = ?,
                    duration_measured_ms = ?,
                    duration_measured_at = ?,
                    duration_delta_ms = 0,
                    duration_status = 'ok',
                    duration_check_version = ?
                WHERE path = ?
                """,
                (
                    1 if dj_only else 0,
                    duration_measured_ms,
                    "manual",
                    manual_id,
                    now_iso,
                    duration_measured_ms,
                    now_iso,
                    duration_version,
                    str(file_path),
                ),
            )
            conn.commit()

        log_payload = {
            "event": "duration_check",
            "timestamp": now_iso,
            "path": str(file_path),
            "source": "manual",
            "track_id": manual_id,
            "is_dj_material": bool(dj_only),
            "duration_ref_ms": duration_measured_ms,
            "duration_measured_ms": duration_measured_ms,
            "duration_delta_ms": 0,
            "duration_status": "ok",
            "thresholds_ms": {"ok": ok_max_ms, "warn": warn_max_ms},
            "check_version": duration_version,
        }
        append_jsonl(resolve_log_path("mgmt_duration"), log_payload)
    finally:
        conn.close()

    click.echo(f"Duration reference set: {manual_id} ({duration_measured_ms} ms)")


_WRAPPER_CONTEXT = dict(ignore_unknown_options=True, help_option_names=[])


@cli.group()
def intake():
    """Canonical intake commands."""


@intake.command("run", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def intake_run(args):
    """Run unified download + intake orchestration."""
    _run_executable("tools/get-intake", args)


@intake.command("prefilter", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def intake_prefilter(args):
    """Run Beatport prefilter against inventory DB."""
    _run_python_script("tools/review/beatport_prefilter.py", args)


@cli.group()
def index():
    """Canonical indexing and metadata registration commands."""


@index.command("register", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def index_register(args):
    """Register files in inventory."""
    _run_dedupe_wrapper(["_mgmt", "register", *list(args)])


@index.command("check", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def index_check(args):
    """Check for duplicates before downloading."""
    _run_dedupe_wrapper(["_mgmt", "check", *list(args)])


@index.command("duration-check", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def index_duration_check(args):
    """Measure durations and compute duration status."""
    _run_dedupe_wrapper(["_mgmt", "check-duration", *list(args)])


@index.command("duration-audit", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def index_duration_audit(args):
    """Audit duration anomalies from inventory."""
    _run_dedupe_wrapper(["_mgmt", "audit-duration", *list(args)])


@index.command("set-duration-ref", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def index_set_duration_ref(args):
    """Set manual duration reference from a known-good file."""
    _run_dedupe_wrapper(["_mgmt", "set-duration-ref", *list(args)])


@index.command("enrich", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def index_enrich(args):
    """Run metadata enrichment for indexed files."""
    _run_dedupe_wrapper(["_metadata", "enrich", *list(args)])


@cli.group()
def decide():
    """Canonical deterministic planning commands."""


@decide.command("profiles")
def decide_profiles():
    """List available policy profiles."""
    from dedupe.policy import list_policy_profiles, load_policy_profile

    names = list_policy_profiles()
    if not names:
        click.echo("No policy profiles found.")
        return
    click.echo("Policy profiles:")
    for name in names:
        profile = load_policy_profile(name)
        click.echo(f"  - {profile.name} ({profile.version}) lane={profile.lane}")


@decide.command("plan")
@click.option("--policy", default="library_balanced", show_default=True, help="Policy profile name")
@click.option("--input", "input_path", type=click.Path(exists=True), required=True, help="Input JSON candidates file")
@click.option("--output", "output_path", type=click.Path(), help="Output JSON plan path")
@click.option("--run-label", default="decide", show_default=True, help="Run label prefix")
def decide_plan(policy, input_path, output_path, run_label):
    """Build deterministic policy-stamped plan from candidate JSON."""
    import json

    from dedupe.decide import PlanCandidate, build_deterministic_plan
    from dedupe.policy import load_policy_profile

    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        raw_candidates = payload.get("candidates", [])
    elif isinstance(payload, list):
        raw_candidates = payload
    else:
        raise click.ClickException("Input JSON must be a list or {'candidates': [...]} object")

    if not isinstance(raw_candidates, list):
        raise click.ClickException("Input candidates must be a JSON list")

    candidates: list[PlanCandidate] = []
    for idx, item in enumerate(raw_candidates, start=1):
        if not isinstance(item, dict):
            raise click.ClickException(f"Candidate #{idx} must be a JSON object")
        path = str(item.get("path", "")).strip()
        if not path:
            raise click.ClickException(f"Candidate #{idx} missing required 'path'")
        match_reasons = item.get("match_reasons", ())
        if isinstance(match_reasons, str):
            match_reasons = [match_reasons]
        if not isinstance(match_reasons, list):
            match_reasons = []
        candidates.append(
            PlanCandidate(
                path=path,
                proposed_action=item.get("proposed_action"),
                proposed_reason=item.get("proposed_reason"),
                match_reasons=tuple(str(v) for v in match_reasons),
                is_dj_material=bool(item.get("is_dj_material", False)),
                duration_status=item.get("duration_status"),
                context=item.get("context", {}) if isinstance(item.get("context"), dict) else {},
            )
        )

    policy_profile = load_policy_profile(policy)
    plan = build_deterministic_plan(candidates, policy_profile, run_label=run_label)
    serialized = plan.to_json(indent=2)
    if output_path:
        output_file = Path(output_path).expanduser().resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(serialized, encoding="utf-8")
        click.echo(f"Wrote plan: {output_file}")
    else:
        click.echo(serialized.rstrip())
    click.echo(f"Plan hash: {plan.plan_hash}")
    click.echo(f"Run id: {plan.run_id}")


@cli.group(name="execute")
def execute_group():
    """Canonical execution commands."""


@execute_group.command("move-plan", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def execute_move_plan(args):
    """Execute move actions from a plan CSV."""
    _run_python_script("tools/review/move_from_plan.py", args)


@execute_group.command("quarantine-plan", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def execute_quarantine_plan(args):
    """Execute quarantine move actions from a plan CSV."""
    _run_python_script("tools/review/quarantine_from_plan.py", args)


@execute_group.command("promote-tags", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def execute_promote_tags(args):
    """Execute promote-by-tags move workflow."""
    _run_python_script("tools/review/promote_by_tags.py", args)


@cli.group()
def verify():
    """Canonical verification commands."""


@verify.command("duration", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def verify_duration(args):
    """Verify duration health status from inventory."""
    _run_dedupe_wrapper(["_mgmt", "audit-duration", *list(args)])


@verify.command("recovery", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def verify_recovery(args):
    """Run recovery verification phase."""
    _run_dedupe_wrapper(["_recover", "--phase", "verify", *list(args)])


@verify.command("parity", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def verify_parity(args):
    """Run legacy-v3 parity validation checks."""
    _run_python_script("scripts/validate_v3_dual_write_parity.py", args)


@verify.command("receipts")
@click.option("--db", type=click.Path(), required=True, help="SQLite DB path")
@click.option("--strict", is_flag=True, help="Return non-zero when warnings are detected")
def verify_receipts(db, strict):
    """Validate move execution receipt consistency in v3 tables."""
    import sqlite3

    from dedupe.storage.schema import init_db

    db_path = Path(db).expanduser().resolve()
    if not db_path.exists():
        raise click.ClickException(f"DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    try:
        totals = {
            "total": conn.execute("SELECT COUNT(*) FROM move_execution").fetchone()[0],
            "moved": conn.execute("SELECT COUNT(*) FROM move_execution WHERE status = 'moved'").fetchone()[0],
            "errors": conn.execute("SELECT COUNT(*) FROM move_execution WHERE status = 'error'").fetchone()[0],
            "missing_dest": conn.execute(
                "SELECT COUNT(*) FROM move_execution WHERE status = 'moved' AND (dest_path IS NULL OR TRIM(dest_path) = '')"
            ).fetchone()[0],
            "missing_plan": conn.execute(
                "SELECT COUNT(*) FROM move_execution WHERE plan_id IS NULL"
            ).fetchone()[0],
        }
    finally:
        conn.close()

    click.echo("Move receipt verification summary:")
    click.echo(f"  total:        {totals['total']}")
    click.echo(f"  moved:        {totals['moved']}")
    click.echo(f"  errors:       {totals['errors']}")
    click.echo(f"  missing_dest: {totals['missing_dest']}")
    click.echo(f"  missing_plan: {totals['missing_plan']}")

    warnings = totals["errors"] + totals["missing_dest"]
    if strict and warnings > 0:
        raise SystemExit(2)


@cli.group()
def report():
    """Canonical reporting and export commands."""


@report.command("m3u")
@click.argument("paths", nargs=-1, type=click.Path(exists=True), required=True)
@click.option("--db", type=click.Path(), help="Database path")
@click.option("--source", help="Source label for playlist naming")
@click.option("--m3u-dir", type=click.Path(), help="Output directory")
@click.option("--merge", is_flag=True, help="Merge all paths into one playlist")
def report_m3u(paths, db, source, m3u_dir, merge):
    """Generate M3U playlists from paths."""
    args: list[str] = ["_mgmt", "--m3u"]
    if merge:
        args.append("--merge")
    if m3u_dir:
        args.extend(["--m3u-dir", str(m3u_dir)])
    if db:
        args.extend(["--db", str(db)])
    if source:
        args.extend(["--source", str(source)])
    for path in paths:
        args.extend(["--path", str(path)])
    _run_dedupe_wrapper(args)


@report.command("duration", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def report_duration(args):
    """Report duration status issues."""
    _run_dedupe_wrapper(["_mgmt", "audit-duration", *list(args)])


@report.command("recovery", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def report_recovery(args):
    """Run recovery report phase."""
    _run_dedupe_wrapper(["_recover", "--phase", "report", *list(args)])


@report.command("plan-summary", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def report_plan_summary(args):
    """Summarize decide plan JSON into table/csv/json views."""
    _run_python_script("tools/review/plan_summary.py", args)


@cli.group()
def auth():
    """Canonical provider authentication commands."""


@auth.command("status", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def auth_status_wrapper(args):
    """Show provider auth/token status."""
    _run_dedupe_wrapper(["_metadata", "auth-status", *list(args)])


@auth.command("init", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def auth_init_wrapper(args):
    """Initialize provider token template file."""
    _run_dedupe_wrapper(["_metadata", "auth-init", *list(args)])


@auth.command("refresh", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def auth_refresh_wrapper(args):
    """Refresh provider access tokens."""
    _run_dedupe_wrapper(["_metadata", "auth-refresh", *list(args)])


@auth.command("login", context_settings=_WRAPPER_CONTEXT)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def auth_login_wrapper(args):
    """Run interactive provider login flows."""
    _run_dedupe_wrapper(["_metadata", "auth-login", *list(args)])


@cli.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
@click.option("--zone", help="Target zone (accepted, staging, etc.)")
@click.option("--move/--no-move", default=False, help="Move files (default: dry-run)")
@click.option("--require-duration-ok", is_flag=True, help="Block promotion unless duration_status is ok")
@click.option("--allow-duration-warn", is_flag=True, help="Allow warn status for manual override")
@click.option("--dj-only", is_flag=True, help="Treat all paths as DJ material")
@click.option("--log", type=click.Path(), help="Log file path (JSONL)")
def recovery(paths, db, zone, move, require_duration_ok, allow_duration_warn, dj_only, log):
    """
    Stub for DJ-safe promotion (duration-aware recovery mode).
    """
    from dedupe.utils.audit_log import append_jsonl, resolve_log_path, now_iso

    log_path = Path(log) if log else resolve_log_path("recovery_decisions")
    append_jsonl(
        log_path,
        {
            "event": "promotion_decision",
            "timestamp": now_iso(),
            "duplicate_group_id": None,
            "is_dj_material": bool(dj_only),
            "chosen_track_path": None,
            "reason": "stub_not_implemented",
            "alternatives": [],
        },
    )

    click.echo("dedupe recovery is a stub (promotion logic not implemented yet).")
    click.echo(f"  Paths: {len(paths)} | zone={zone} | move={move}")
    if require_duration_ok:
        click.echo("  Duration gate: require duration_status=ok")
    if allow_duration_warn:
        click.echo("  Override: allow duration_status=warn (manual)")


if __name__ == "__main__":
    cli()
