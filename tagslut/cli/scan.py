"""tagslut scan CLI group."""

from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

import click

from tagslut.scan.discovery import discover_paths
from tagslut.scan.orchestrator import run_scan as orchestrator_run_scan
from tagslut.storage.schema import get_connection, init_db
from tagslut.utils.db import resolve_db_path


@click.group("scan", hidden=True)
def scan_group() -> None:
    """Scan queue and run management commands."""


def _resolve_scan_db(
    db: Optional[str | Path],
    *,
    purpose: str,
    allow_create: bool,
) -> Path:
    resolution = resolve_db_path(
        str(db) if db is not None else None,
        purpose=purpose,
        allow_create=allow_create,
    )
    return resolution.path


def _connect_scan_db(
    db: Optional[str | Path],
    *,
    purpose: str,
    allow_create: bool,
) -> sqlite3.Connection:
    db_path = _resolve_scan_db(db, purpose=purpose, allow_create=allow_create)
    conn = get_connection(str(db_path), purpose=purpose, allow_create=allow_create)
    if purpose == "write":
        init_db(conn)
    conn.row_factory = sqlite3.Row
    return conn


def _call_with_optional_db(func, *args, db):  # type: ignore  # TODO: mypy-strict
    """Call monkeypatched helpers with backward-compatible signatures in tests."""
    parameters = inspect.signature(func).parameters
    if "db" in parameters:
        return func(*args, db=db)
    return func(*args)


def enqueue_scan(root: Path, priority: int, db: Optional[str | Path] = None) -> int:
    """Enqueue discoverable files under root into a new scan run and return run_id."""
    conn = _connect_scan_db(db, purpose="write", allow_create=True)
    try:
        now_row = conn.execute("SELECT CURRENT_TIMESTAMP").fetchone()
        now = str(now_row[0]) if now_row is not None else None
        payload = json.dumps({"status": "QUEUED", "priority": int(priority)})
        with conn:
            conn.execute(
                """
                INSERT INTO scan_runs (library_root, mode, created_at, tool_versions_json)
                VALUES (?, 'initial', ?, ?)
                """,
                (str(root), now, payload),
            )
            run_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])

            for path in discover_paths(root):
                conn.execute(
                    """
                    INSERT INTO scan_queue (run_id, path, size_bytes, mtime_ns, stage, state)
                    VALUES (?, ?, ?, ?, 0, 'PENDING')
                    """,
                    (run_id, str(path), path.stat().st_size, path.stat().st_mtime_ns),
                )
        return run_id
    finally:
        conn.close()


def run_scan_job(run_id: Optional[int], db: Optional[str | Path] = None) -> list[str]:
    """Execute a scan run via orchestrator and return progress lines."""
    conn = _connect_scan_db(db, purpose="write", allow_create=True)
    try:
        selected_run_id: Optional[int] = run_id
        if selected_run_id is None:
            row = conn.execute("SELECT id, library_root FROM scan_runs ORDER BY id DESC LIMIT 1").fetchone()
            if row is None:
                raise click.ClickException("No scan runs found. Enqueue first with 'tagslut scan enqueue'.")
            selected_run_id = int(row["id"])
            library_root = Path(str(row["library_root"]))
            prefix = [f"Resuming latest scan run {selected_run_id}"]
        else:
            row = conn.execute(
                "SELECT id, library_root FROM scan_runs WHERE id = ?",
                (selected_run_id,),
            ).fetchone()
            if row is None:
                raise click.ClickException(f"Scan run not found: {selected_run_id}")
            library_root = Path(str(row["library_root"]))
            prefix = [f"Running scan {selected_run_id}"]

        new_run_id = int(orchestrator_run_scan(conn, library_root))
        summary = conn.execute(
            """
            SELECT
                SUM(CASE WHEN state = 'PENDING' THEN 1 ELSE 0 END) AS queued,
                SUM(CASE WHEN state = 'DONE' THEN 1 ELSE 0 END) AS done,
                SUM(CASE WHEN state = 'FAILED' THEN 1 ELSE 0 END) AS failed
            FROM scan_queue
            WHERE run_id = ?
            """,
            (new_run_id,),
        ).fetchone()
        done = int(summary["done"] or 0)
        failed = int(summary["failed"] or 0)
        queued = int(summary["queued"] or 0)
        return [
            *prefix,
            f"Started run {new_run_id} for {library_root}",
            f"Progress: done={done} failed={failed} queued={queued}",
            "Run complete",
        ]
    finally:
        conn.close()


def get_status_rows(db: Optional[str | Path] = None) -> list[dict[str, Any]]:
    """Read run status rows from DB."""
    conn = _connect_scan_db(db, purpose="read", allow_create=False)
    try:
        rows = conn.execute(
            """
            SELECT
                sr.id AS run_id,
                COALESCE(
                    json_extract(sr.tool_versions_json, '$.status'),
                    CASE WHEN sr.completed_at IS NOT NULL THEN 'COMPLETE' ELSE 'RUNNING' END
                ) AS status,
                SUM(CASE WHEN sq.state = 'PENDING' THEN 1 ELSE 0 END) AS queued,
                SUM(CASE WHEN sq.state = 'DONE' THEN 1 ELSE 0 END) AS done,
                SUM(CASE WHEN sq.state = 'FAILED' THEN 1 ELSE 0 END) AS failed,
                sr.created_at AS started_at
            FROM scan_runs sr
            LEFT JOIN scan_queue sq ON sq.run_id = sr.id
            GROUP BY sr.id, sr.tool_versions_json, sr.completed_at, sr.created_at
            ORDER BY sr.id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_issue_rows(
    run_id: int,
    severity: Optional[str],
    db: Optional[str | Path] = None,
) -> list[dict[str, Any]]:
    """Read issue counts for a run, optionally filtered by severity."""
    conn = _connect_scan_db(db, purpose="read", allow_create=False)
    try:
        where = ["run_id = ?"]
        params: list[Any] = [run_id]
        if severity:
            where.append("UPPER(severity) = UPPER(?)")
            params.append(severity)

        query = (
            "SELECT severity, issue_code, COUNT(*) AS count "
            "FROM scan_issues "
            f"WHERE {' AND '.join(where)} "
            "GROUP BY severity, issue_code"
        )
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_report_rows(run_id: int, db: Optional[str | Path] = None) -> tuple[list[dict[str, Any]], int]:
    """Read per-issue report rows and format-duplicate count for a run."""
    conn = _connect_scan_db(db, purpose="read", allow_create=False)
    try:
        issue_rows = conn.execute(
            """
            SELECT issue_code, COUNT(*) AS count
            FROM scan_issues
            WHERE run_id = ?
            GROUP BY issue_code
            ORDER BY count DESC, issue_code
            """,
            (run_id,),
        ).fetchall()
        format_duplicate_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM files f
            WHERE f.scan_status = 'FORMAT_DUPLICATE'
              AND EXISTS (
                  SELECT 1 FROM scan_queue q
                  WHERE q.run_id = ? AND q.path = f.path
              )
            """,
            (run_id,),
        ).fetchone()[0]
        return [dict(row) for row in issue_rows], int(format_duplicate_count or 0)
    finally:
        conn.close()


@scan_group.command("enqueue")
@click.option(
    "--root",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),  # type: ignore
)  # TODO: mypy-strict
@click.option("--priority", default=5, show_default=True, type=int)
@click.option("--db", type=click.Path(path_type=Path), help="Database path (auto-detect from env if not provided)")
def scan_enqueue(root: Path, priority: int, db: Optional[Path]) -> None:
    """Enqueue files under ROOT for scanning."""
    run_id = _call_with_optional_db(enqueue_scan, root, priority, db=db)
    click.echo(f"Enqueued scan run {run_id} for {root} with priority={priority}")


@scan_group.command("run")
@click.option("--run-id", type=int, default=None)
@click.option("--db", type=click.Path(path_type=Path), help="Database path (auto-detect from env if not provided)")
def scan_run(run_id: Optional[int], db: Optional[Path]) -> None:
    """Run scanner for a specific run-id or resume latest."""
    for line in _call_with_optional_db(run_scan_job, run_id, db=db):
        click.echo(line)


@scan_group.command("status")
@click.option("--db", type=click.Path(path_type=Path), help="Database path (auto-detect from env if not provided)")
def scan_status(db: Optional[Path]) -> None:
    """Print scan run summary table."""
    rows = _call_with_optional_db(get_status_rows, db=db)
    click.echo("run_id | status | queued | done | failed | started_at")
    for row in rows:
        click.echo(
            f"{row['run_id']} | {row['status']} | {row['queued']} | "
            f"{row['done']} | {row['failed']} | {row['started_at']}"
        )


@scan_group.command("issues")
@click.option("--run-id", required=True, type=int)
@click.option("--severity", default=None)
@click.option("--db", type=click.Path(path_type=Path), help="Database path (auto-detect from env if not provided)")
def scan_issues(run_id: int, severity: Optional[str], db: Optional[Path]) -> None:
    """Print issues table for a run, optionally filtered by severity."""
    rows = _call_with_optional_db(get_issue_rows, run_id, severity, db=db)
    order = {"ERROR": 3, "WARN": 2, "INFO": 1}
    rows = sorted(rows, key=lambda r: order.get(str(r["severity"]).upper(), 0), reverse=True)

    click.echo("severity | issue_code | count")
    for row in rows:
        click.echo(f"{row['severity']} | {row['issue_code']} | {row['count']}")


@scan_group.command("report")
@click.option("--run-id", required=True, type=int)
@click.option("--db", type=click.Path(path_type=Path), help="Database path (auto-detect from env if not provided)")
def scan_report(run_id: int, db: Optional[Path]) -> None:
    """Print per-issue-code counts + FORMAT_DUPLICATE count."""
    issue_rows, format_duplicate_count = _call_with_optional_db(get_report_rows, run_id, db=db)
    click.echo("issue_code | count")
    for row in issue_rows:
        click.echo(f"{row['issue_code']} | {row['count']}")
    click.echo(f"FORMAT_DUPLICATE | {format_duplicate_count}")
