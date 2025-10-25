"""Audio Suite package.

This package provides a unified toolkit for managing local FLAC libraries,
matching playlist files against your library and streaming providers, and
downloading new tracks.  It draws inspiration from the **sluttools** and
**flaccid** projects, but has been reimplemented from the ground up with a
modular architecture and a permissive license.

The public API is intentionally narrow.  Most interactions occur through
command‑line subcommands defined in :mod:`audio_suite.cli`.  Internal
modules under :mod:`audio_suite.core`, :mod:`audio_suite.plugins`,
:mod:`audio_suite.get` and :mod:`audio_suite.tui` are subject to change
without notice.
"""

__all__ = [
    "cli",
    "core",
    "get",
    "plugins",
    "tui",
]