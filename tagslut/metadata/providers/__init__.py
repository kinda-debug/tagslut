"""
Metadata providers package.

Each provider implements the AbstractProvider interface for fetching
track metadata from external services.
"""

from tagslut.metadata.providers.base import AbstractProvider, RateLimiter
from tagslut.metadata.providers.beatport import BeatportProvider
from tagslut.metadata.providers.qobuz import QobuzProvider
from tagslut.metadata.providers.tidal import TidalProvider
from tagslut.metadata.providers.tagslut_api_client import (
    TagslutApiClientConfig,
    build_client,
    get_client,
    load_config_from_env,
    reset_client_cache,
)
from tagslut.metadata.providers.tagslut_validation import (
    lookup_isrc,
    smoke_test,
    validate_token,
)

__all__ = [
    "AbstractProvider",
    "RateLimiter",
    "BeatportProvider",
    "TidalProvider",
    "QobuzProvider",
    "TagslutApiClientConfig",
    "load_config_from_env",
    "build_client",
    "get_client",
    "reset_client_cache",
    "validate_token",
    "lookup_isrc",
    "smoke_test",
]
