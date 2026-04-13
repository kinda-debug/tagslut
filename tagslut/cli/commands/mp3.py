"""CLI commands for MP3 derivative management.

  tagslut mp3 build      — transcode preferred FLAC masters to MP3 and register in mp3_asset
  tagslut mp3 reconcile  — scan an existing MP3 root and link files to canonical identities
"""
from __future__ import annotations

import sys

import click

CANONICAL_PIPELINE_TEXT = (
    "Current DJ workflow: curate → transcode → M3U → Rekordbox."
)


@click.group(
    "mp3",
    help="""
\b
Build and reconcile MP3 derivative assets in MP3_LIBRARY.

Common subcommands:
  build, reconcile

See: tagslut dj --help
""",
    epilog="""
\b
Examples:
    tagslut intake <provider-url>
  tagslut mp3 reconcile --db <path> --scan-csv <path>
  tagslut mp3 build --db <path> --dj-root <path> --execute

Next: tagslut dj --help
""",
)
def mp3_group() -> None:
    """Build and reconcile MP3 derivative assets."""


@mp3_group.command(
    "build",
    help=f"Build MP3s from canonical FLAC masters. {CANONICAL_PIPELINE_TEXT}",
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
    "reconcile-library",
    help=(
        "Reconcile an existing MP3 root with the database (legacy direct scan). "
        f"{CANONICAL_PIPELINE_TEXT}"
    ),
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option(
    "--mp3-root",
    required=False,
    default=None,
    help=(
        "Canonical MP3 asset root to reconcile. Defaults to "
        "$MP3_LIBRARY. Preserved source/staging folders "
        "(for example /Volumes/MUSIC/staging or /Volumes/MUSIC/_work) stay "
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
def mp3_reconcile_library(
    db_path: str | None,
    mp3_root: str | None,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Scan an existing MP3 root and link files to canonical identities in mp3_asset.

    Uses one active MP3 asset root (MP3_LIBRARY).
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
        or os.environ.get("MP3_LIBRARY")
        or ""
    )
    if not resolved_mp3_root:
        raise click.ClickException(
            "Missing --mp3-root (or set MP3_LIBRARY)."
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
    help=f"Scan MP3 root directories and write a manifest CSV. {CANONICAL_PIPELINE_TEXT}",
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
@click.option("--include-gig-runs", is_flag=True, default=False, help="Allow scanning gig_runs roots (off by default).")
@click.option("--force", is_flag=True, default=False, help="Re-run even if checkpoint marks Task 2 done.")
def mp3_scan(
    db_path: str | None,
    mp3_roots: tuple,
    out_csv: str,
    run_id: str,
    log_dir: str,
    include_gig_runs: bool,
    force: bool,
) -> None:
    """Scan MP3 root directories and write a manifest CSV."""
    from pathlib import Path
    from tagslut.exec.mp3_build import scan_mp3_roots
    from tagslut.utils.reconcile_session import (
        ensure_session_run_id,
        format_completed_tasks,
        task_done,
        update_checkpoint,
    )

    checkpoints_dir = Path("data/checkpoints")
    _run_id, checkpoint = ensure_session_run_id(
        run_id_arg=run_id,
        checkpoints_dir=checkpoints_dir,
    )
    if checkpoint is not None:
        click.echo(f"[CHECKPOINT] {checkpoint.path} tasks done: {format_completed_tasks(checkpoint)}")
        if task_done(checkpoint, 2) and not force:
            if not click.confirm("Task 2 is marked done. Re-run anyway?", default=False):
                return

    roots = [Path(r) for r in mp3_roots]
    exclude = None
    if not include_gig_runs:
        exclude = [r"/_work/gig_runs/"]
    result = scan_mp3_roots(
        roots=roots,
        out_csv=Path(out_csv),
        run_id=_run_id,
        log_dir=Path(log_dir),
        exclude_patterns=exclude,
    )
    zones = len(roots)
    click.echo(
        f"[TASK 2 COMPLETE] {result.total} files scanned across {zones} zones. CSV: {result.csv_path}"
    )
    if result.errors:
        click.secho(f"  {len(result.errors)} error(s) during scan.", fg="yellow", err=True)

    ckpt_path = update_checkpoint(
        checkpoints_dir=checkpoints_dir,
        run_id=_run_id,
        task_number=2,
        notes=f"CSV: {result.csv_path} | total={result.total} errors={len(result.errors)}",
    )
    click.echo(f"[CHECKPOINT SAVED] {ckpt_path}")

def _run_reconcile_scan(
    *,
    resolved_db: Path,
    scan_csv: Path,
    out_json: Path,
    run_id: str,
    log_dir: Path,
    dry_run: bool,
    force: bool,
) -> None:
    import sqlite3

    from tagslut.exec.mp3_build import reconcile_mp3_scan
    from tagslut.utils.reconcile_session import (
        format_completed_tasks,
        find_latest_checkpoint_for_run_id,
        task_done,
        update_checkpoint,
    )

    checkpoints_dir = Path("data/checkpoints")
    checkpoint = find_latest_checkpoint_for_run_id(checkpoints_dir, run_id=run_id)
    if checkpoint is not None:
        click.echo(f"[CHECKPOINT] {checkpoint.path} tasks done: {format_completed_tasks(checkpoint)}")
        if task_done(checkpoint, 3) and not force:
            if not click.confirm("Task 3 is marked done. Re-run anyway?", default=False):
                return

    conn = sqlite3.connect(str(resolved_db))
    try:
        result = reconcile_mp3_scan(
            conn,
            scan_csv=scan_csv,
            run_id=run_id,
            log_dir=log_dir,
            out_json=out_json,
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

    ckpt_path = update_checkpoint(
        checkpoints_dir=checkpoints_dir,
        run_id=run_id,
        task_number=3,
        notes=f"scan_csv={scan_csv} out_json={out_json} dry_run={dry_run} "
              f"t1={t1} t2={t2} t3={t3} fuzzy={fuzzy} stubs={stubs} conflicts={conflicts} "
              f"skipped={skipped} errors={errors}",
    )
    click.echo(f"[CHECKPOINT SAVED] {ckpt_path}")


@mp3_group.command(
    "reconcile",
    help=f"Reconcile a scan CSV against the DB using multi-tier matching. {CANONICAL_PIPELINE_TEXT}",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option("--scan-csv", "scan_csv", required=True, type=click.Path(exists=True), help="Scan CSV from mp3 scan.")
@click.option("--out", "out_json", default=None, type=str, help="Output JSON summary path.")
@click.option("--run-id", "run_id", default="", help="Session run ID.")
@click.option("--log-dir", "log_dir", default="data/logs", help="Directory for JSONL logs.")
@click.option("--dry-run/--execute", default=True, show_default=True, help="Dry-run counts without writing.")
@click.option("--force", is_flag=True, default=False, help="Re-run even if checkpoint marks Task 3 done.")
def mp3_reconcile_scan(
    db_path: str | None,
    scan_csv: str,
    out_json: str | None,
    run_id: str,
    log_dir: str,
    dry_run: bool,
    force: bool,
) -> None:
    """Reconcile a scan CSV against the DB using multi-tier matching."""
    from datetime import datetime
    from pathlib import Path

    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path
    from tagslut.utils.reconcile_session import ensure_session_run_id

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    _run_id, _ = ensure_session_run_id(
        run_id_arg=run_id,
        checkpoints_dir=Path("data/checkpoints"),
    )
    today = datetime.now().strftime("%Y%m%d")
    _out_json = out_json or f"data/mp3_reconcile_{today}.json"
    log_path = Path(log_dir)
    _run_reconcile_scan(
        resolved_db=Path(resolved_db),
        scan_csv=Path(scan_csv),
        out_json=Path(_out_json),
        run_id=_run_id,
        log_dir=log_path,
        dry_run=dry_run,
        force=force,
    )


@mp3_group.command(
    "reconcile-scan",
    help=f"(Alias) Reconcile a scan CSV against the DB. {CANONICAL_PIPELINE_TEXT}",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option("--scan-csv", "scan_csv", required=True, type=click.Path(exists=True), help="Scan CSV from mp3 scan.")
@click.option("--out", "out_json", default=None, type=str, help="Output JSON summary path.")
@click.option("--run-id", "run_id", default="", help="Session run ID.")
@click.option("--log-dir", "log_dir", default="data/logs", help="Directory for JSONL logs.")
@click.option("--dry-run/--execute", default=True, show_default=True, help="Dry-run counts without writing.")
@click.option("--force", is_flag=True, default=False, help="Re-run even if checkpoint marks Task 3 done.")
def mp3_reconcile_scan_alias(
    db_path: str | None,
    scan_csv: str,
    out_json: str | None,
    run_id: str,
    log_dir: str,
    dry_run: bool,
    force: bool,
) -> None:
    from datetime import datetime
    from pathlib import Path

    from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path
    from tagslut.utils.reconcile_session import ensure_session_run_id

    try:
        resolved_db = resolve_cli_env_db_path(
            db_path, purpose="write", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    _run_id, _ = ensure_session_run_id(
        run_id_arg=run_id,
        checkpoints_dir=Path("data/checkpoints"),
    )
    today = datetime.now().strftime("%Y%m%d")
    _out_json = out_json or f"data/mp3_reconcile_{today}.json"
    _run_reconcile_scan(
        resolved_db=Path(resolved_db),
        scan_csv=Path(scan_csv),
        out_json=Path(_out_json),
        run_id=_run_id,
        log_dir=Path(log_dir),
        dry_run=dry_run,
        force=force,
    )


@mp3_group.command("verify-schema", help="Task 1: verify DJ/MP3 reconciliation tables exist.")
@click.option("--db", "db_path", required=True, type=click.Path(exists=True), help="Path to tagslut SQLite DB.")
@click.option("--run-id", "run_id", default="", help="Session run ID.")
@click.option("--force", is_flag=True, default=False, help="Re-run even if checkpoint marks Task 1 done.")
def mp3_verify_schema(db_path: str, run_id: str, force: bool) -> None:
    import sqlite3
    import json
    from pathlib import Path
    from datetime import datetime, timezone

    from tagslut.utils.reconcile_session import (
        ensure_session_run_id,
        format_completed_tasks,
        task_done,
        update_checkpoint,
    )

    checkpoints_dir = Path("data/checkpoints")
    _run_id, checkpoint = ensure_session_run_id(
        run_id_arg=run_id,
        checkpoints_dir=checkpoints_dir,
    )
    if checkpoint is not None:
        click.echo(f"[CHECKPOINT] {checkpoint.path} tasks done: {format_completed_tasks(checkpoint)}")
        if task_done(checkpoint, 1) and not force:
            if not click.confirm("Task 1 is marked done. Re-run anyway?", default=False):
                return

    conn = sqlite3.connect(str(Path(db_path)))
    try:
        rows = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table'
              AND name IN ('mp3_asset','dj_admission','dj_track_id_map',
                           'dj_playlist','dj_playlist_track','dj_export_state',
                           'reconcile_log')
            ORDER BY name
            """
        ).fetchall()
    finally:
        conn.close()

    present = {str(r[0]) for r in rows}
    required = {
        "mp3_asset",
        "dj_admission",
        "dj_track_id_map",
        "dj_playlist",
        "dj_playlist_track",
        "dj_export_state",
        "reconcile_log",
    }
    missing = sorted(required - present)
    click.echo(f"[TASK 1 COMPLETE] {len(present)} tables verified existing, {len(missing)} tables missing.")
    if missing:
        click.secho(f"Missing: {', '.join(missing)}", fg="red", err=True)

    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = log_dir / f"reconcile_schema_{_run_id}.jsonl"
    with open(jsonl_path, "a", encoding="utf-8") as jsonl_fh:
        jsonl_fh.write(
            json.dumps(
                {
                    "ts": datetime.now(tz=timezone.utc).isoformat(),
                    "run_id": _run_id,
                    "action": "schema_verified",
                    "path": str(Path(db_path)),
                    "result": "ok" if not missing else "missing",
                    "details": {"present": sorted(present), "missing": missing},
                }
            )
            + "\n"
        )

    ckpt_path = update_checkpoint(
        checkpoints_dir=checkpoints_dir,
        run_id=_run_id,
        task_number=1,
        notes=f"present={sorted(present)} missing={missing}",
    )
    click.echo(f"[CHECKPOINT SAVED] {ckpt_path}")


@mp3_group.command(
    "missing-masters",
    help=f"Report orphaned MP3s and FLACs without MP3s. {CANONICAL_PIPELINE_TEXT}",
)
@click.option("--db", "db_path", default=None, help="Path to tagslut SQLite DB.")
@click.option("--out", "out_path", default=None, help="Output .md path (default: data/missing_masters_YYYYMMDD.md)")
@click.option("--run-id", "run_id", default="", help="Session run ID.")
@click.option("--log-dir", "log_dir", default="data/logs", help="Directory for JSONL logs.")
@click.option("--force", is_flag=True, default=False, help="Re-run even if checkpoint marks Task 7 done.")
def mp3_missing_masters(
    db_path: str | None,
    out_path: str | None,
    run_id: str,
    log_dir: str,
    force: bool,
) -> None:
    """Generate a missing-masters Markdown report."""
    import sqlite3
    from datetime import datetime
    from pathlib import Path

    from tagslut.exec.mp3_build import generate_missing_masters_report
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
            db_path, purpose="read", source_label="--db"
        ).path
    except DbResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    today = datetime.now().strftime("%Y%m%d")
    _out_path = Path(out_path) if out_path else Path(f"data/missing_masters_{today}.md")

    checkpoints_dir = Path("data/checkpoints")
    _run_id, _ = ensure_session_run_id(run_id_arg=run_id, checkpoints_dir=checkpoints_dir)
    checkpoint = find_latest_checkpoint_for_run_id(checkpoints_dir, run_id=_run_id)
    if checkpoint is not None:
        click.echo(f"[CHECKPOINT] {checkpoint.path} tasks done: {format_completed_tasks(checkpoint)}")
        if task_done(checkpoint, 7) and not force:
            if not click.confirm("Task 7 is marked done. Re-run anyway?", default=False):
                return

    conn = sqlite3.connect(str(resolved_db))
    try:
        result = generate_missing_masters_report(
            conn,
            out_path=_out_path,
            run_id=_run_id,
            log_dir=Path(log_dir),
        )
    finally:
        conn.close()

    click.echo(
        f"[TASK 7 COMPLETE] "
        f"Section A: {result['section_a_count']} orphaned MP3s "
        f"(HIGH={result['high']} MEDIUM={result['medium']} LOW={result['low']}) | "
        f"Section B: {result['section_b_count']} FLACs with no MP3. "
        f"Report: {_out_path}"
    )

    ckpt_path = update_checkpoint(
        checkpoints_dir=checkpoints_dir,
        run_id=_run_id,
        task_number=7,
        notes=f"out={_out_path} section_a={result['section_a_count']} "
              f"high={result['high']} medium={result['medium']} low={result['low']} "
              f"section_b={result['section_b_count']}",
    )
    click.echo(f"[CHECKPOINT SAVED] {ckpt_path}")
