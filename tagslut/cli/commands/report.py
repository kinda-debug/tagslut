from __future__ import annotations

import click

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
        run_tagslut_wrapper(args)

    @report.command("duration", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def report_duration(args):  # type: ignore  # TODO: mypy-strict
        """Report duration status issues."""
        run_tagslut_wrapper(["_mgmt", "audit-duration", *list(args)])

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
