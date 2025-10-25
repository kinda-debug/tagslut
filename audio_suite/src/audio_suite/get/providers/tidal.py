"""Tidal provider for Audio Suite.

This module is analogous to :mod:`audio_suite.get.providers.qobuz`.  It
implements a stub download function that creates a placeholder FLAC file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def download_track(identifier: str, settings, output: Optional[Path]) -> Path:
    """Download a track by ID or URL and return the path to the saved file.

    The current implementation does not perform any network calls; it
    writes an empty file named after the identifier.  Future
    implementations should authenticate against Tidal, fetch metadata and
    download the highest available quality.
    """
    if output is None:
        directory = Path("~/Music/Downloads").expanduser()
        filename = f"{identifier}.flac"
        path = directory / filename
    else:
        if output.suffix:
            path = output
        else:
            directory = output
            filename = f"{identifier}.flac"
            path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path