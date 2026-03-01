from __future__ import annotations

import click

from tagslut.cli.commands._index_helpers import run_audit_duration, run_report_m3u
from tagslut.cli.runtime import run_python_script, run_tagslut_wrapper, WRAPPER_CONTEXT


def register_report_group(cli: click.Group) -> None:
    @cli.group()
    def report():  # type: ignore  # TODO: mypy-strict
        """Canonical reporting and export commands."""

    @report.command("m3u")
    @click.argument("paths", nargs=-1, type=click.Path(exists=True), required=True)
    @click.option("--db", type=click.Path(), help="Database path")
    @click.option("--source", help="Source label for playlist naming")
    @click.option("--m3u-dir", type=click.Path(), help="Output directory")
    @click.option("--merge", is_flag=True, help="Merge all paths into one playlist")
    def report_m3u(paths, db, source, m3u_dir, merge):  # type: ignore  # TODO: mypy-strict
        """Generate M3U playlists from paths."""
        run_report_m3u(
            paths=tuple(paths),
            merge=merge,
            m3u_dir=m3u_dir,
            db=db,
            source=source,
        )

    @report.command("duration")
    @click.option("--db", type=click.Path(), help="Database path (auto-detect from env if not provided)")
    @click.option("--dj-only", is_flag=True, help="Only DJ material")
    @click.option("--status", "status_filter", help="Comma-separated statuses (warn,fail,unknown)")
    @click.option("--source", help="Filter by download source")
    @click.option("--since", help="Filter by download_date >= YYYY-MM-DD")
    @click.option("--inactive-exclude", is_flag=True, help="Exclude mgmt_status=inactive")
    def report_duration(  # type: ignore  # TODO: mypy-strict
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

    @report.command("recovery", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def report_recovery(args):  # type: ignore  # TODO: mypy-strict
        """Run recovery report phase."""
        run_tagslut_wrapper(["_recover", "--phase", "report", *list(args)])

    @report.command("plan-summary", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def report_plan_summary(args):  # type: ignore  # TODO: mypy-strict
        """Summarize decide plan JSON into table/csv/json views."""
        run_python_script("tools/review/plan_summary.py", args)
