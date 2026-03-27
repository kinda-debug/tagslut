from __future__ import annotations

import click

from tagslut.cli.commands._index_helpers import run_audit_duration, run_report_m3u
from tagslut.cli.runtime import run_python_script, WRAPPER_CONTEXT


def register_report_group(cli: click.Group) -> None:
    @cli.group()
    def report():  # type: ignore  # TODO: mypy-strict
        """Canonical reporting and export commands."""

    @report.command("m3u")
    @click.argument("paths", nargs=-1, type=click.Path(exists=True), required=False)
    @click.option(
        "--paths-file",
        type=click.Path(exists=True),
        help="Text file with one path per line (avoids command line length limits).",
    )
    @click.option("--db", type=click.Path(), help="Database path")
    @click.option("--source", help="Source label for playlist naming")
    @click.option("--m3u-dir", type=click.Path(), help="Output directory")
    @click.option(
        "--path-mode",
        type=click.Choice(["absolute", "relative"], case_sensitive=False),
        default="absolute",
        show_default=True,
        help="Write absolute or playlist-relative paths",
    )
    @click.option(
        "--name-prefix",
        default="",
        help="Prefix added to the generated playlist name",
    )
    @click.option(
        "--name-suffix",
        default="",
        help="Suffix added to the generated playlist name",
    )
    @click.option("--merge", is_flag=True, help="Merge all paths into one playlist")
    @click.option("--verbose", is_flag=True, help="Print extra details about playlist generation")
    def report_m3u(  # type: ignore  # TODO: mypy-strict
        paths,
        paths_file,
        db,
        source,
        m3u_dir,
        path_mode,
        name_prefix,
        name_suffix,
        merge,
        verbose,
    ):
        """Generate M3U playlists from paths."""
        selected_paths = list(paths or ())
        if paths_file:
            with open(paths_file, "r", encoding="utf-8", errors="replace") as handle:
                for raw in handle.read().splitlines():
                    text = raw.strip()
                    if not text or text.startswith("#"):
                        continue
                    selected_paths.append(text)
        run_report_m3u(
            paths=tuple(selected_paths),
            merge=merge,
            m3u_dir=m3u_dir,
            db=db,
            source=source,
            path_mode=str(path_mode),
            name_prefix=str(name_prefix),
            name_suffix=str(name_suffix),
            verbose=bool(verbose),
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

    @report.command("plan-summary", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def report_plan_summary(args):  # type: ignore  # TODO: mypy-strict
        """Summarize decide plan JSON into table/csv/json views."""
        run_python_script("tools/review/plan_summary.py", args)

    @report.command("dj-review")
    @click.option("--db", required=True, type=click.Path(), help="Inventory DB path")
    @click.option("--port", default=5000, show_default=True, type=int, help="Port to listen on")
    @click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind")
    @click.option("--open-browser/--no-open-browser", default=True, help="Open browser on launch")
    def report_dj_review(db, port, host, open_browser):  # type: ignore  # TODO: mypy-strict
        """Launch local DJ track review web app."""
        try:
            from tagslut._web.review_app import run_review_app
        except ImportError as exc:
            raise click.ClickException(
                "Flask is required. Install with: pip install tagslut[web]"
            ) from exc

        run_review_app(db=db, port=port, host=host, open_browser=open_browser)
