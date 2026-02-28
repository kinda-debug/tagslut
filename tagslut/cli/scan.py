"""tagslut scan CLI group."""

from pathlib import Path
from typing import Any, Optional

import click


@click.group("scan", hidden=True)
def scan_group() -> None:
    """Scan queue and run management commands."""


def enqueue_scan(root: Path, priority: int) -> int:
    """Placeholder enqueue hook. Returns run_id."""
    return 1


def run_scan_job(run_id: Optional[int]) -> list[str]:
    """Placeholder run hook. Returns progress lines."""
    if run_id is None:
        return ["Resuming latest scan run", "Progress: 100%", "Run complete"]
    return [f"Running scan {run_id}", "Progress: 100%", "Run complete"]


def get_status_rows() -> list[dict[str, Any]]:
    """Placeholder status hook."""
    return []


def get_issue_rows(run_id: int, severity: Optional[str]) -> list[dict[str, Any]]:
    """Placeholder issues hook."""
    _ = severity
    return []


def get_report_rows(run_id: int) -> tuple[list[dict[str, Any]], int]:
    """Placeholder report hook."""
    _ = run_id
    return ([], 0)


@scan_group.command("enqueue")
@click.option("--root", required=True, type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--priority", default=5, show_default=True, type=int)
def scan_enqueue(root: Path, priority: int) -> None:
    """Enqueue files under ROOT for scanning."""
    run_id = enqueue_scan(root, priority)
    click.echo(f"Enqueued scan run {run_id} for {root} with priority={priority}")


@scan_group.command("run")
@click.option("--run-id", type=int, default=None)
def scan_run(run_id: Optional[int]) -> None:
    """Run scanner for a specific run-id or resume latest."""
    for line in run_scan_job(run_id):
        click.echo(line)


@scan_group.command("status")
def scan_status() -> None:
    """Print scan run summary table."""
    rows = get_status_rows()
    click.echo("run_id | status | queued | done | failed | started_at")
    for row in rows:
        click.echo(
            f"{row['run_id']} | {row['status']} | {row['queued']} | "
            f"{row['done']} | {row['failed']} | {row['started_at']}"
        )


@scan_group.command("issues")
@click.option("--run-id", required=True, type=int)
@click.option("--severity", default=None)
def scan_issues(run_id: int, severity: Optional[str]) -> None:
    """Print issues table for a run, optionally filtered by severity."""
    rows = get_issue_rows(run_id, severity)
    order = {"ERROR": 3, "WARN": 2, "INFO": 1}
    rows = sorted(rows, key=lambda r: order.get(str(r["severity"]).upper(), 0), reverse=True)

    click.echo("severity | issue_code | count")
    for row in rows:
        click.echo(f"{row['severity']} | {row['issue_code']} | {row['count']}")


@scan_group.command("report")
@click.option("--run-id", required=True, type=int)
def scan_report(run_id: int) -> None:
    """Print per-issue-code counts + FORMAT_DUPLICATE count."""
    issue_rows, format_duplicate_count = get_report_rows(run_id)
    click.echo("issue_code | count")
    for row in issue_rows:
        click.echo(f"{row['issue_code']} | {row['count']}")
    click.echo(f"FORMAT_DUPLICATE | {format_duplicate_count}")
