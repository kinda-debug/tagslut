"""Compatibility re-export for track hub CLI."""

from tagslut.cli.commands.track_hub_cli import main
from tagslut.cli.commands.track_hub_cli import *  # noqa: F401,F403


if __name__ == "__main__":
    main()
