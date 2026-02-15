"""
Metadata enrichment package for tagslut.

This package provides functionality to:
- Fetch metadata from external providers (Spotify, Beatport, Qobuz, Tidal)
- Resolve track identity using ISRC, provider IDs, or text search
- Apply cascading rules to select canonical metadata values
- Evaluate file health by comparing durations
"""

from tagslut.metadata.models.types import ProviderTrack, EnrichmentResult
from tagslut.metadata.auth import TokenManager

__all__ = [
    "ProviderTrack",
    "EnrichmentResult",
    "TokenManager",
]
