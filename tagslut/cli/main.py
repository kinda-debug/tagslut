"""
CLI Entry Point for Tagslut

Contains only:
- Top-level Click group registration
- Command group imports from tagslut.cli.commands.*
- Global Click options/context setup

All command implementations live in tagslut/cli/commands/*.py
"""

import logging
import sys
from pathlib import Path

import click

from tagslut.cli.commands.auth import register_auth_group
from tagslut.cli.commands.decide import register_decide_group
from tagslut.cli.commands.dj import dj_group
from tagslut.cli.commands.mp3 import mp3_group
from tagslut.cli.commands.export import export_group
from tagslut.cli.commands.execute import register_execute_group
from tagslut.cli.commands.gig import gig_group
from tagslut.cli.commands.index import register_index_group
from tagslut.cli.commands.intake import register_intake_group
from tagslut.cli.commands.library import register_library_group
from tagslut.cli.commands.tag import register_tag_group
from tagslut.cli.commands.report import register_report_group
from tagslut.cli.commands.ops import register_ops_group
from tagslut.cli.commands.verify import register_verify_group
from tagslut.cli.commands.misc import register_misc_commands

# Add project root to path so we can import tools as modules if needed
sys.path.insert(0, str(Path(__file__).parents[2]))

logger = logging.getLogger("tagslut")

_TRANSITIONAL_COMMAND_REPLACEMENTS: dict[str, str] = {
    "tagslut _mgmt": "tagslut index ... / tagslut report m3u ...",
    "tagslut _metadata": "tagslut auth ... / tagslut index enrich ...",
    "tagslut _recover": "Recovery is retired; see legacy/tagslut_recovery/ for the archived workflow.",
}


def _format_transitional_warning(command: str) -> str:
    replacement = _TRANSITIONAL_COMMAND_REPLACEMENTS.get(command)
    message = (
        f"DEPRECATION NOTICE: '{command}' is a transitional legacy wrapper. "
        "Use canonical entrypoints from docs/SCRIPT_SURFACE.md."
    )
    if replacement:
        message += f" Recommended now: `{replacement}`."
    return message


def _warn_transitional_command(command: str) -> None:
    click.secho(_format_transitional_warning(command), fg="yellow", err=True)


class _TagslutGroup(click.Group):
    """CLI group that can emit alias warnings before help handling."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        return super().parse_args(ctx, args)


@click.group(cls=_TagslutGroup)
@click.version_option(version="3.0.0")
def cli():  # type: ignore  # TODO: mypy-strict
    """Tagslut CLI."""


# Register canonical command groups
register_intake_group(cli)
register_index_group(cli)
register_decide_group(cli)
register_execute_group(cli)
register_verify_group(cli)
register_report_group(cli)
register_auth_group(cli)
register_ops_group(cli)
register_library_group(cli)
register_tag_group(cli)

# Register DJ, export, gig, and MP3 groups
cli.add_command(dj_group)
cli.add_command(export_group, name="export")
cli.add_command(gig_group, name="gig")
cli.add_command(mp3_group, name="mp3")

# Register standalone misc commands (`init` is operator-facing; debug/stub
# helpers are hidden from top-level help).
register_misc_commands(cli)


if __name__ == "__main__":
    cli()
