"""Provider registry for Audio Suite.

Submodules in this package implement support for individual streaming services.
Providers should implement a ``download_track(identifier: str, settings, output: Optional[Path]) -> Path``
function that returns the location of the downloaded FLAC file.
"""

from . import qobuz, tidal  # noqa: F401

__all__ = ["qobuz", "tidal"]