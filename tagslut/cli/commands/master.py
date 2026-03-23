"""CLI commands for MASTER_LIBRARY operations."""
from __future__ import annotations

import click


@click.group("master", help="MASTER_LIBRARY operations.")
def master_group() -> None:
    pass


@master_group.command("scan", help="Scan MASTER_LIBRARY tree and register asset_file rows.")
@click.option(
    "--root",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Root directory of MASTER_LIBRARY (FLAC tree).",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option("--run-id", "run_id", default="", help="Session run ID.")
@click.option("--log-dir", "log_dir", default="data/logs", help="Directory for JSONL logs.")
@click.option(
    "--dry-run/--execute",
    default=True,
    show_default=True,
    help="Dry-run counts without writing to DB.",
)
def master_scan(
    root: str,
    db_path: str | None,
    run_id: str,
    log_dir: str,
    dry_run: bool,
) -> None:
    """Scan the MASTER_LIBRARY FLAC tree and register asset_file + asset_link rows."""
    import sqlite3
    from pathlib import Path

    from tagslut.exec.master_scan import scan_master_library
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    _run_id = run_id or "a655f8d4-c88b-4986-8a92-8e952848a75d"

    conn = sqlite3.connect(str(resolved_db))
    try:
        result = scan_master_library(
            conn,
            master_root=Path(root),
            run_id=_run_id,
            log_dir=Path(log_dir),
            dry_run=dry_run,
        )
    finally:
        conn.close()

    inserted = result.get("assets_inserted", 0)
    matched = result.get("matched_existing", 0)
    stubs = result.get("stubs_created", 0)
    skipped = result.get("skipped_existing", 0)
    errors = result.get("errors", 0)

    click.echo(
        f"[TASK 6 COMPLETE] "
        f"inserted={inserted} matched={matched} stubs={stubs} "
        f"skipped={skipped} errors={errors}"
    )
    if dry_run:
        click.secho("Dry-run complete. Pass --execute to commit.", fg="yellow")
