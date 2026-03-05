"""Compatibility re-export for track hub CLI.

The track hub CLI implementation now lives in tagslut.cli.commands.track_hub_cli.
"""

from tagslut.cli.commands.track_hub_cli import *  # type: ignore  # noqa: F401,F403


if __name__ == "__main__":
    main()
