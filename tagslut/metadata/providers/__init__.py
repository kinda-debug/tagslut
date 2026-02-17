"""
Metadata providers package.

Each provider implements the AbstractProvider interface for fetching
track metadata from external services.
"""

from tagslut.metadata.providers.base import AbstractProvider, RateLimiter
from tagslut.metadata.providers.spotify import SpotifyProvider
from tagslut.metadata.providers.beatport import BeatportProvider
from tagslut.metadata.providers.qobuz import QobuzProvider
from tagslut.metadata.providers.deezer import DeezerProvider
from tagslut.metadata.providers.tidal import TidalProvider
from tagslut.metadata.providers.itunes import iTunesProvider
from tagslut.metadata.providers.apple_music import AppleMusicProvider

__all__ = [
    "AbstractProvider",
    "RateLimiter",
    "SpotifyProvider",
    "BeatportProvider",
    "QobuzProvider",
    "DeezerProvider",
    "TidalProvider",
    "iTunesProvider",
    "AppleMusicProvider",
]
