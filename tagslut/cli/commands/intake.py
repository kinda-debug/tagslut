from __future__ import annotations

import click

from tagslut.cli.runtime import run_executable, run_python_script, WRAPPER_CONTEXT


def register_intake_group(cli: click.Group) -> None:
    @cli.group()
    def intake():  # type: ignore  # TODO: mypy-strict
        """Canonical intake commands."""

    @intake.command("run", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def intake_run(args):  # type: ignore  # TODO: mypy-strict
        """Run unified download + intake orchestration."""
        run_executable("tools/get-intake", args)

    @intake.command("prefilter", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def intake_prefilter(args):  # type: ignore  # TODO: mypy-strict
        """Run Beatport prefilter against inventory DB."""
        run_python_script("tools/review/beatport_prefilter.py", args)
