"""CLI commands for MP3 derivative management.

  tagslut mp3 build      — transcode preferred FLAC masters to MP3 and register in mp3_asset
  tagslut mp3 reconcile  — scan an existing MP3 root and link files to canonical identities
"""
from __future__ import annotations

import sys

import click

CANONICAL_PIPELINE_TEXT = (
    "Canonical curated-library flow: Stage 1 `tagslut intake`; "
    "Stage 2 `tagslut mp3 build` or `tagslut mp3 reconcile`; "
    "Stage 3 `tagslut dj backfill`, then `tagslut dj validate`; "
    "Stage 4 `tagslut dj xml emit` or `tagslut dj xml patch`."
)


@click.group(
    "mp3",
    help="""
\b
Build and reconcile MP3 derivative assets.

Part of the 4-stage DJ pipeline:
    Stage 1: intake      → Refresh canonical masters via tagslut intake
    Stage 2: build       → Transcode canonical FLAC masters to DJ MP3s
                     reconcile   → Register existing DJ MP3s against canonical identities
    Stage 3: dj backfill → Admit verified MP3s into DJ state
                     dj validate → Verify DJ library state before XML export
                     dj admit    → One-off manual admission when backfill is not the right tool
    Stage 4: dj xml emit / dj xml patch

Common subcommands:
  build, reconcile

See: tagslut dj --help (Stages 3-4)
Docs: docs/DJ_PIPELINE.md
""",
    epilog="""
\b
Examples:
    tagslut intake <provider-url>
  tagslut mp3 reconcile --db <path> --mp3-root <path>
  tagslut mp3 build --db <path> --dj-root <path> --execute

Next: tagslut dj --help (Stages 3-4)
Then: tagslut dj backfill --db <path>
""",
)
def mp3_group() -> None:
    """Build and reconcile MP3 derivative assets."""


@mp3_group.command(
    "build",
    help=f"Build MP3s from canonical FLAC masters. Stage 2a of the 4-stage pipeline. {CANONICAL_PIPELINE_TEXT}",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option(
    "--dj-root",
    required=True,
    help="Output directory for transcoded MP3 files.",
    type=click.Path(file_okay=False, writable=True),
)
@click.option(
    "--identity-ids",
    default=None,
    help="Comma-separated identity IDs to build (default: all un-built identities).",
)
@click.option(
    "--dry-run/--execute",
    default=True,
    show_default=True,
    help="Dry-run counts what would be built without writing anything.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print per-item progress to stderr.",
)
def mp3_build(
    db_path: str | None,
    dj_root: str,
    identity_ids: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Transcode preferred FLAC masters to MP3 and register in mp3_asset.

    Only processes identities that do not already have an mp3_asset row
    with status='verified'. Safe to re-run (idempotent).
    """
    import sqlite3
    from pathlib import Path

    from tagslut.exec.mp3_build import build_mp3_from_identity
    from tagslut.cli._progress import make_progress_cb
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    ids: list[int] | None = None
    if identity_ids:
        try:
            ids = [int(x.strip()) for x in identity_ids.split(",") if x.strip()]
        except ValueError as exc:
            raise click.ClickException(f"Invalid --identity-ids: {exc}") from exc

    conn = sqlite3.connect(str(resolved_db))
    try:
        cb = make_progress_cb(verbose)
        result = build_mp3_from_identity(
            conn,
            identity_ids=ids,
            dj_root=Path(dj_root),
            dry_run=dry_run,
            progress_cb=cb,
        )
    finally:
        conn.close()

    click.echo(result.summary())
    if result.errors:
        for err in result.errors:
            click.secho(f"  error: {err}", fg="red", err=True)

    if dry_run and result.built > 0:
        click.secho(
            f"Dry-run complete. Pass --execute to build {result.built} MP3(s).",
            fg="yellow",
        )

    sys.exit(1 if result.failed > 0 else 0)


@mp3_group.command(
    "reconcile",
    help=(
        "Reconcile an existing MP3 root with the database. "
        f"Stage 2b of the 4-stage pipeline. Next: tagslut dj backfill. {CANONICAL_PIPELINE_TEXT}"
    ),
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option(
    "--mp3-root",
    required=False,
    default=None,
    help=(
        "Canonical MP3 asset root to reconcile. Defaults to "
        "$DJ_LIBRARY, then $MP3_LIBRARY. Preserved source/staging folders "
        "(for example /Volumes/MUSIC/mdl or /Volumes/MUSIC/_work) stay "
        "reference-only and are not active roots."
    ),
    type=click.Path(exists=True, file_okay=False),
)
@click.option(
    "--dry-run/--execute",
    default=True,
    show_default=True,
    help="Dry-run counts what would be linked without writing anything.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print per-item progress to stderr.",
)
def mp3_reconcile(
    db_path: str | None,
    mp3_root: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Scan an existing MP3 root and link files to canonical identities in mp3_asset.

    Uses one active MP3 asset root (DJ_LIBRARY aliasing MP3_LIBRARY).
    Source/staging folders remain provenance-only inputs. Matches via ISRC tag
    first, then title+artist. Files that already have an mp3_asset row are
    skipped. Safe to re-run (idempotent).
    """
    import os
    import sqlite3
    from pathlib import Path

    from tagslut.exec.mp3_build import reconcile_mp3_library
    from tagslut.cli._progress import make_progress_cb
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    resolved_mp3_root = (
        mp3_root
        or os.environ.get("DJ_LIBRARY")
        or os.environ.get("MP3_LIBRARY")
        or ""
    )
    if not resolved_mp3_root:
        raise click.ClickException(
            "Missing --mp3-root (or set DJ_LIBRARY / MP3_LIBRARY)."
        )
    mp3_root_path = Path(resolved_mp3_root).expanduser()
    if not mp3_root_path.exists() or not mp3_root_path.is_dir():
        raise click.ClickException(f"MP3 root does not exist or is not a directory: {mp3_root_path}")

    conn = sqlite3.connect(str(resolved_db))
    try:
        cb = make_progress_cb(verbose)
        result = reconcile_mp3_library(
            conn,
            mp3_root=mp3_root_path,
            dry_run=dry_run,
            progress_cb=cb,
        )
    finally:
        conn.close()

    click.echo(result.summary())
    if verbose and result.errors:
        for err in result.errors:
            click.echo(f"  {err}")
    elif result.errors:
        click.secho(
            f"  {len(result.errors)} file(s) had errors or no identity match "
            "(use --verbose to list them).",
            fg="yellow",
        )

    if dry_run and result.linked > 0:
        click.secho(
            f"Dry-run complete. Pass --execute to register {result.linked} MP3(s).",
            fg="yellow",
        )


@mp3_group.command(
    "scan",
    help=f"Scan MP3 root directories and write a manifest CSV. Outside the canonical 4-stage curated-library flow. {CANONICAL_PIPELINE_TEXT}",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB (unused, kept for consistency).")
@click.option(
    "--mp3-roots",
    "mp3_roots",
    multiple=True,
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Root directory of MP3 files to scan (may be specified multiple times).",
)
@click.option("--out", "out_csv", required=True, type=str, help="Output CSV path.")
@click.option("--run-id", "run_id", default="", help="Session run ID.")
@click.option("--log-dir", "log_dir", default="data/logs", help="Directory for JSONL logs.")
def mp3_scan(
    db_path: str | None,
    mp3_roots: tuple,
    out_csv: str,
    run_id: str,
    log_dir: str,
) -> None:
    """Scan MP3 root directories and write a manifest CSV."""
    from pathlib import Path
    from tagslut.exec.mp3_build import scan_mp3_roots

    _run_id = run_id or "a655f8d4-c88b-4986-8a92-8e952848a75d"
    roots = [Path(r) for r in mp3_roots]
    result = scan_mp3_roots(
        roots=roots,
        out_csv=Path(out_csv),
        run_id=_run_id,
        log_dir=Path(log_dir),
    )
    zones = len(roots)
    click.echo(
        f"[TASK 2 COMPLETE] {result.total} files scanned across {zones} zones. CSV: {result.csv_path}"
    )
    if result.errors:
        click.secho(f"  {len(result.errors)} error(s) during scan.", fg="yellow", err=True)


@mp3_group.command(
    "reconcile-scan",
    help=f"Reconcile a scan CSV against the DB using multi-tier matching. Outside the canonical 4-stage curated-library flow. {CANONICAL_PIPELINE_TEXT}",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option("--scan-csv", "scan_csv", required=True, type=click.Path(exists=True), help="Scan CSV from mp3 scan.")
@click.option("--out", "out_json", default=None, type=str, help="Output JSON summary path.")
@click.option("--run-id", "run_id", default="", help="Session run ID.")
@click.option("--log-dir", "log_dir", default="data/logs", help="Directory for JSONL logs.")
@click.option("--dry-run/--execute", default=True, show_default=True, help="Dry-run counts without writing.")
def mp3_reconcile_scan(
    db_path: str | None,
    scan_csv: str,
    out_json: str | None,
    run_id: str,
    log_dir: str,
    dry_run: bool,
) -> None:
    """Reconcile a scan CSV against the DB using multi-tier matching."""
    import sqlite3
    from datetime import datetime
    from pathlib import Path

    from tagslut.exec.mp3_build import reconcile_mp3_scan
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    _run_id = run_id or "a655f8d4-c88b-4986-8a92-8e952848a75d"
    _out_json = out_json or f"data/logs/reconcile_scan_{_run_id}.json"
    log_path = Path(log_dir)

    conn = sqlite3.connect(str(resolved_db))
    try:
        result = reconcile_mp3_scan(
            conn,
            scan_csv=Path(scan_csv),
            run_id=_run_id,
            log_dir=log_path,
            out_json=Path(_out_json),
            dry_run=dry_run,
        )
    finally:
        conn.close()

    t1 = result.get("matched_t1", 0)
    t2 = result.get("matched_t2", 0)
    t3 = result.get("matched_t3", 0)
    fuzzy = result.get("fuzzy", 0)
    stubs = result.get("stubs", 0)
    conflicts = result.get("conflicts", 0)
    skipped = result.get("skipped", 0)
    errors = result.get("errors", 0)

    click.echo(
        f"[TASK 3 COMPLETE] "
        f"t1={t1} t2={t2} t3={t3} fuzzy={fuzzy} stubs={stubs} "
        f"conflicts={conflicts} skipped={skipped} errors={errors}"
    )
    if dry_run:
        click.secho("Dry-run complete. Pass --execute to commit.", fg="yellow")


@mp3_group.command(
    "missing-masters",
    help=f"Report orphaned MP3s and FLACs without MP3s. Outside the canonical 4-stage curated-library flow. {CANONICAL_PIPELINE_TEXT}",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option("--out", "out_path", default=None, help="Output .md path (default: data/missing_masters_YYYYMMDD.md)")
def mp3_missing_masters(
    db_path: str | None,
    out_path: str | None,
) -> None:
    """Generate a missing-masters Markdown report."""
    import sqlite3
    from datetime import datetime
    from pathlib import Path

    from tagslut.exec.mp3_build import generate_missing_masters_report
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="read", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    today = datetime.now().strftime("%Y%m%d")
    _out_path = Path(out_path) if out_path else Path(f"data/missing_masters_{today}.md")

    conn = sqlite3.connect(str(resolved_db))
    try:
        result = generate_missing_masters_report(conn, out_path=_out_path)
    finally:
        conn.close()

    click.echo(
        f"[TASK 7 COMPLETE] "
        f"Section A: {result['section_a_count']} orphaned MP3s "
        f"(HIGH={result['high']} MEDIUM={result['medium']} LOW={result['low']}) | "
        f"Section B: {result['section_b_count']} FLACs with no MP3. "
        f"Report: {_out_path}"
    )
