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
@click.option("--force", is_flag=True, default=False, help="Re-run even if checkpoint marks Task 6 done.")
def master_scan(
    root: str,
    db_path: str | None,
    run_id: str,
    log_dir: str,
    dry_run: bool,
    force: bool,
) -> None:
    """Scan the MASTER_LIBRARY FLAC tree and register asset_file + asset_link rows."""
    import sqlite3
    from pathlib import Path

    from tagslut.exec.master_scan import scan_master_library
    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path
    from tagslut.utils.reconcile_session import (
        ensure_session_run_id,
        find_latest_checkpoint_for_run_id,
        format_completed_tasks,
        task_done,
        update_checkpoint,
    )

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    checkpoints_dir = Path("data/checkpoints")
    _run_id, _ = ensure_session_run_id(run_id_arg=run_id, checkpoints_dir=checkpoints_dir)
    checkpoint = find_latest_checkpoint_for_run_id(checkpoints_dir, run_id=_run_id)
    if checkpoint is not None:
        click.echo(f"[CHECKPOINT] {checkpoint.path} tasks done: {format_completed_tasks(checkpoint)}")
        if task_done(checkpoint, 6) and not force:
            if not click.confirm("Task 6 is marked done. Re-run anyway?", default=False):
                return

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

    ckpt_path = update_checkpoint(
        checkpoints_dir=checkpoints_dir,
        run_id=_run_id,
        task_number=6,
        notes=f"root={root} dry_run={dry_run} inserted={inserted} matched={matched} stubs={stubs} skipped={skipped} errors={errors}",
    )
    click.echo(f"[CHECKPOINT SAVED] {ckpt_path}")
