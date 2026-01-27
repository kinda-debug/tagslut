"""
Metadata providers package.

Each provider implements the AbstractProvider interface for fetching
track metadata from external services.
"""

from dedupe.metadata.providers.base import AbstractProvider, RateLimiter
from dedupe.metadata.providers.spotify import SpotifyProvider

__all__ = [
    "AbstractProvider",
    "RateLimiter",
    "SpotifyProvider",
]
