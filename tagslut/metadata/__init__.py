
"""
Metadata enrichment package for tagslut.

**Active providers:** Beatport, TIDAL, Qobuz

Qobuz is active in enrichment/tagging flows, but remains non-authoritative for identity promotion without corroboration. Do not treat it as a canonical identity source without the explicit evidence gate.

This package provides functionality to:
- Fetch metadata from external providers (Beatport, TIDAL, Qobuz)
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
