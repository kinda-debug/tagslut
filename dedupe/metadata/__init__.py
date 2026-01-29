"""
Metadata enrichment package for dedupe.

This package provides functionality to:
- Fetch metadata from external providers (Spotify, Beatport, Qobuz, Tidal)
- Resolve track identity using ISRC, provider IDs, or text search
- Apply cascading rules to select canonical metadata values
- Evaluate file health by comparing durations
"""

from dedupe.metadata.models.types import ProviderTrack, EnrichmentResult
from dedupe.metadata.auth import TokenManager

__all__ = [
    "ProviderTrack",
    "EnrichmentResult",
    "TokenManager",
]
