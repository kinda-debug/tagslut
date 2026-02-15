"""Metadata enrichment utilities."""

from .artwork import ArtworkFetcher
from .enrichment import MetadataEnricher
from .lyrics import LyricsFetcher, StaticLyricsFetcher
from .schema import EnrichedAlbum, EnrichedTrack

__all__ = [
    "ArtworkFetcher",
    "MetadataEnricher",
    "LyricsFetcher",
    "StaticLyricsFetcher",
    "EnrichedAlbum",
    "EnrichedTrack",
]
