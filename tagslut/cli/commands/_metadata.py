"""Internal metadata enrichment group and auth helpers."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import click

from tagslut.cli.runtime import collect_flac_paths as _collect_flac_paths

logger = logging.getLogger("tagslut")


def _local_file_info_from_path(file_path: Path):
    from tagslut.core.metadata import extract_metadata
    from tagslut.metadata.models.types import LocalFileInfo

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


def _tidal_device_login(token_manager) -> None:
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


def _qobuz_login(token_manager) -> None:
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


def _beatport_token_input(token_manager) -> None:
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


def register_metadata_group(cli: click.Group) -> None:
    @cli.group(name="_metadata", hidden=True)
    def metadata():
        """Internal metadata enrichment commands."""

    @metadata.command()
    @click.option('--db', type=click.Path(), required=False, help='Database path')
    @click.option('--path', type=str, help='Filter files by path pattern (SQL LIKE) or file/dir in --standalone mode')
    @click.option('--zones', type=str, help='Comma-separated zones to include (e.g. accepted,staging)')
    @click.option('--providers', default='beatport,tidal,deezer,itunes', help='Comma-separated list of providers (order = priority)')
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
            tagslut index enrich --db music.db --hoarding --providers beatport,tidal,deezer --execute

            # Both modes: health check + full metadata
            tagslut index enrich --db music.db --recovery --hoarding --execute

            # Filter by path pattern
            tagslut index enrich --db music.db --recovery --path "/Volumes/Music/DJ/%" --execute
        """
        from tagslut.metadata.enricher import Enricher
        from tagslut.metadata.auth import TokenManager
        from tagslut.storage.schema import init_db
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
            for p in stats.no_match_files[:10]:
                # Show just the filename
                click.echo(f"  • {Path(p).name}")
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
        from tagslut.metadata.auth import TokenManager, DEFAULT_TOKENS_PATH

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
        from tagslut.metadata.auth import TokenManager, DEFAULT_TOKENS_PATH

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
        from tagslut.metadata.auth import TokenManager, DEFAULT_TOKENS_PATH

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
        from tagslut.metadata.auth import TokenManager, DEFAULT_TOKENS_PATH

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
