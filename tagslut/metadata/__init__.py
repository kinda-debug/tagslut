
"""
Metadata enrichment package for tagslut.

**Active providers:** Beatport, TIDAL
**Legacy/future providers:** Qobuz, Spotify, Apple Music, iTunes

Only Beatport and TIDAL are currently active and supported in the enrichment pipeline. Other providers are legacy, historical, or future/aspirational. Do not treat them as active without explicit contract change.

This package provides functionality to:
- Fetch metadata from external providers (Beatport, TIDAL)
- Resolve track identity using ISRC, provider IDs, or text search
- Apply cascading rules to select canonical metadata values
- Evaluate file health by comparing durations

<!-- Future agents: Do not treat legacy/future providers as active without explicit contract change. -->
"""

from tagslut.metadata.models.types import ProviderTrack, EnrichmentResult
from tagslut.metadata.auth import TokenManager

__all__ = [
    "ProviderTrack",
    "EnrichmentResult",
    "TokenManager",
]
