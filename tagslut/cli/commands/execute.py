from __future__ import annotations

import click

from tagslut.cli.runtime import run_python_script, WRAPPER_CONTEXT


def register_execute_group(cli: click.Group) -> None:
    @cli.group(name="execute")
    def execute_group():
        """Canonical execution commands."""

    @execute_group.command("move-plan", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def execute_move_plan(args):
        """Execute move actions from a plan CSV."""
        run_python_script("tools/review/move_from_plan.py", args)

    @execute_group.command("quarantine-plan", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def execute_quarantine_plan(args):
        """Execute quarantine move actions from a plan CSV."""
        run_python_script("tools/review/quarantine_from_plan.py", args)

    @execute_group.command("promote-tags", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def execute_promote_tags(args):
        """Execute promote-by-tags move workflow."""
        run_python_script("tools/review/promote_by_tags.py", args)
