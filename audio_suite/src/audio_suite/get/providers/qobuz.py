"""Qobuz provider for Audio Suite.

This module implements a minimal interface for downloading FLAC tracks from
Qobuz.  It is a stub and does not perform any real network operations.  In
production, this module would authenticate using credentials stored via
``keyring``, call the Qobuz API to retrieve a download URL and then save
the resulting file to disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def download_track(identifier: str, settings, output: Optional[Path]) -> Path:
    """Download a track by ID or URL and return the path to the saved file.

    This stubbed implementation simply writes an empty FLAC file to the
    desired location.  If ``output`` is a directory, the file name is
    generated from the identifier.  The default output directory is
    ``~/Music/Downloads``.
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
    # Write a zero‑length file as a placeholder
    path.write_bytes(b"")
    return path