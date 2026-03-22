"""
Metadata providers package.

Each provider implements the AbstractProvider interface for fetching
track metadata from external services.
"""

from tagslut.metadata.providers.base import AbstractProvider, RateLimiter
from tagslut.metadata.providers.beatport import BeatportProvider
from tagslut.metadata.providers.tidal import TidalProvider

__all__ = [
    "AbstractProvider",
    "RateLimiter",
    "BeatportProvider",
    "TidalProvider",
]
