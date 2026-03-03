"""V3 policy helpers."""

from tagslut.policy.v3.staleness import (
    DEFAULT_ENRICHMENT_MAX_AGE_SECONDS,
    is_enrichment_stale,
    is_hash_stale,
    is_integrity_stale,
)

__all__ = [
    "DEFAULT_ENRICHMENT_MAX_AGE_SECONDS",
    "is_enrichment_stale",
    "is_hash_stale",
    "is_integrity_stale",
]

