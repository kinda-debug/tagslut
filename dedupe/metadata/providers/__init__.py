"""
Metadata providers package.

Each provider implements the AbstractProvider interface for fetching
track metadata from external services.
"""

from dedupe.metadata.providers.base import AbstractProvider, RateLimiter
from dedupe.metadata.providers.spotify import SpotifyProvider
from dedupe.metadata.providers.beatport import BeatportProvider
from dedupe.metadata.providers.qobuz import QobuzProvider
from dedupe.metadata.providers.tidal import TidalProvider
from dedupe.metadata.providers.itunes import iTunesProvider
from dedupe.metadata.providers.apple_music import AppleMusicProvider

__all__ = [
    "AbstractProvider",
    "RateLimiter",
    "SpotifyProvider",
    "BeatportProvider",
    "QobuzProvider",
    "TidalProvider",
    "iTunesProvider",
    "AppleMusicProvider",
]
