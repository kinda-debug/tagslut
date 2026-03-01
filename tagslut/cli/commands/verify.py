from __future__ import annotations

from pathlib import Path

import click

from tagslut.cli.commands._index_helpers import run_audit_duration
from tagslut.cli.runtime import run_python_script, run_tagslut_wrapper, WRAPPER_CONTEXT


def register_verify_group(cli: click.Group) -> None:
    @cli.group()
    def verify():  # type: ignore  # TODO: mypy-strict
        """Canonical verification commands."""

    @verify.command("duration")
    @click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
    @click.option("--dj-only", is_flag=True, help="Only DJ material")
    @click.option("--status", "status_filter", help="Comma-separated statuses (warn,fail,unknown)")
    @click.option("--source", help="Filter by download source")
    @click.option("--since", help="Filter by download_date >= YYYY-MM-DD")
    @click.option("--inactive-exclude", is_flag=True, help="Exclude mgmt_status=inactive")
    def verify_duration(  # type: ignore  # TODO: mypy-strict
        db,
        dj_only,
        status_filter,
        source,
        since,
        inactive_exclude,
    ):
        """
        Report files with duration_status != ok (or filtered statuses).
        """
        run_audit_duration(
            db=db,
            dj_only=dj_only,
            status_filter=status_filter,
            source=source,
            since=since,
            inactive_exclude=inactive_exclude,
        )

    @verify.command("recovery", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def verify_recovery(args):  # type: ignore  # TODO: mypy-strict
        """Run recovery verification phase."""
        run_tagslut_wrapper(["_recover", "--phase", "verify", *list(args)])

    @verify.command("parity", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def verify_parity(args):  # type: ignore  # TODO: mypy-strict
        """Run legacy-v3 parity validation checks."""
        run_python_script("scripts/validate_v3_dual_write_parity.py", args)

    @verify.command("receipts")
    @click.option("--db", type=click.Path(), required=True, help="SQLite DB path")
    @click.option("--strict", is_flag=True, help="Return non-zero when warnings are detected")
    def verify_receipts(db, strict):  # type: ignore  # TODO: mypy-strict
        """Validate move execution receipt consistency in v3 tables."""
        import sqlite3

        from tagslut.storage.schema import init_db

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
                    "SELECT COUNT(*) FROM move_execution"
                    " WHERE status = 'moved' AND (dest_path IS NULL OR TRIM(dest_path) = '')"
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
