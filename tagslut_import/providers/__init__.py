"""Provider implementations for Tagslut."""

from .apple_music import AppleMusicProvider
from .base import MusicProvider
from .musicbrainz import MusicBrainzProvider
from .qobuz import QobuzProvider
from .spotify import SpotifyProvider
from .tidal import TidalProvider

__all__ = [
    "AppleMusicProvider",
    "MusicProvider",
    "MusicBrainzProvider",
    "QobuzProvider",
    "SpotifyProvider",
    "TidalProvider",
]
