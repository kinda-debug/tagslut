"""Models for metadata enrichment."""

from dedupe.metadata.models.types import (
    MatchConfidence,
    MetadataHealth,
    ProviderTrack,
    EnrichmentResult,
    LocalFileInfo,
)
from dedupe.metadata.models.precedence import (
    DURATION_PRECEDENCE,
    BPM_PRECEDENCE,
    KEY_PRECEDENCE,
    GENRE_PRECEDENCE,
    SUB_GENRE_PRECEDENCE,
    LABEL_PRECEDENCE,
    CATALOG_NUMBER_PRECEDENCE,
    TITLE_PRECEDENCE,
    ARTIST_PRECEDENCE,
    ALBUM_PRECEDENCE,
    ARTWORK_PRECEDENCE,
    AUDIO_FEATURES_SOURCE,
)

__all__ = [
    "MatchConfidence",
    "MetadataHealth",
    "ProviderTrack",
    "EnrichmentResult",
    "LocalFileInfo",
    "DURATION_PRECEDENCE",
    "BPM_PRECEDENCE",
    "KEY_PRECEDENCE",
    "GENRE_PRECEDENCE",
    "SUB_GENRE_PRECEDENCE",
    "LABEL_PRECEDENCE",
    "CATALOG_NUMBER_PRECEDENCE",
    "TITLE_PRECEDENCE",
    "ARTIST_PRECEDENCE",
    "ALBUM_PRECEDENCE",
    "ARTWORK_PRECEDENCE",
    "AUDIO_FEATURES_SOURCE",
]
