"""
Data models for metadata enrichment.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum


class MatchConfidence(str, Enum):
    """Match confidence levels for provider track matches."""
    EXACT = "exact"        # Matched by ISRC or provider ID
    STRONG = "strong"      # Title + artist match, duration within tolerance
    MEDIUM = "medium"      # Partial match, duration close
    WEAK = "weak"          # Only duration matches
    NONE = "none"          # No usable match


class MetadataHealth(str, Enum):
    """File health status based on duration comparison."""
    OK = "ok"
    SUSPECT_TRUNCATED = "suspect_truncated"
    SUSPECT_EXTENDED = "suspect_extended"
    UNKNOWN = "unknown"


@dataclass
class ProviderTrack:
    """
    Normalized track metadata from a single provider.

    This represents the result of fetching a track from any provider,
    normalized into a common format for comparison and cascading.
    """
    service: str                      # spotify, qobuz, tidal, beatport, apple
    service_track_id: str
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    duration_ms: Optional[int] = None
    isrc: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    genre: Optional[str] = None
    label: Optional[str] = None
    year: Optional[int] = None
    album_art_url: Optional[str] = None
    url: Optional[str] = None
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    explicit: Optional[bool] = None
    match_confidence: MatchConfidence = MatchConfidence.NONE
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_s(self) -> Optional[float]:
        """Duration in seconds."""
        if self.duration_ms is not None:
            return self.duration_ms / 1000.0
        return None


@dataclass
class EnrichmentResult:
    """
    Result of enrichment for a single file.

    Contains the canonical metadata values after applying cascade rules,
    plus all provider matches for auditing.
    """
    path: str

    # Canonical values (after cascade)
    canonical_bpm: Optional[float] = None
    canonical_key: Optional[str] = None
    canonical_genre: Optional[str] = None
    canonical_isrc: Optional[str] = None
    canonical_label: Optional[str] = None
    canonical_year: Optional[int] = None
    canonical_duration: Optional[float] = None
    canonical_duration_source: Optional[str] = None

    # Health evaluation
    metadata_health: MetadataHealth = MetadataHealth.UNKNOWN
    metadata_health_reason: Optional[str] = None

    # Match info
    enrichment_confidence: MatchConfidence = MatchConfidence.NONE
    enrichment_providers: List[str] = field(default_factory=list)

    # All provider matches (for auditing)
    matches: List[ProviderTrack] = field(default_factory=list)

    # Resolution log for debugging
    log: List[str] = field(default_factory=list)


@dataclass
class LocalFileInfo:
    """
    Local file information extracted from database and tags.

    Used as input to the resolution state machine.
    """
    path: str
    measured_duration_s: Optional[float] = None

    # From tags
    tag_artist: Optional[str] = None
    tag_title: Optional[str] = None
    tag_album: Optional[str] = None
    tag_isrc: Optional[str] = None
    tag_label: Optional[str] = None
    tag_year: Optional[int] = None

    # Known provider IDs (if any)
    spotify_id: Optional[str] = None
    qobuz_id: Optional[str] = None
    tidal_id: Optional[str] = None
    beatport_id: Optional[str] = None
    apple_id: Optional[str] = None

    # Fingerprint info
    acoustid_id: Optional[str] = None
    musicbrainz_id: Optional[str] = None


# Precedence rules for cascading
DURATION_PRECEDENCE = ["beatport", "qobuz", "tidal", "spotify", "apple"]
BPM_PRECEDENCE = ["beatport", "qobuz", "tidal", "spotify"]
KEY_PRECEDENCE = ["beatport", "qobuz", "tidal", "spotify"]
GENRE_PRECEDENCE = ["beatport", "qobuz", "tidal", "spotify"]
ARTWORK_PRECEDENCE = ["qobuz", "tidal", "spotify", "beatport", "apple"]
