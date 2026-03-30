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


CONFIDENCE_NUMERIC: dict[MatchConfidence, float] = {
    MatchConfidence.EXACT: 1.0,
    MatchConfidence.STRONG: 0.85,
    MatchConfidence.MEDIUM: 0.70,
    MatchConfidence.WEAK: 0.55,
    MatchConfidence.NONE: 0.0,
}


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
    service: str                      # tidal, beatport
    service_track_id: str

    # Core identity
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_id: Optional[str] = None
    isrc: Optional[str] = None
    url: Optional[str] = None                 # Link to track on service

    # Timing / position
    duration_ms: Optional[int] = None
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    year: Optional[int] = None
    release_date: Optional[str] = None        # Full date string

    # DJ-essential
    bpm: Optional[float] = None
    key: Optional[str] = None                 # Musical key (e.g. "F# min")
    key_scale: Optional[str] = None
    tone_tags: Optional[List[str]] = None
    popularity: Optional[float] = None
    genre: Optional[str] = None
    sub_genre: Optional[str] = None           # Beatport sub-genre
    acousticness: Optional[float] = None
    danceability: Optional[float] = None
    energy: Optional[float] = None
    instrumentalness: Optional[float] = None
    loudness: Optional[float] = None
    valence: Optional[float] = None

    # Release info
    label: Optional[str] = None
    catalog_number: Optional[str] = None      # Beatport
    mix_name: Optional[str] = None            # "Original Mix", "Radio Edit", etc.
    version: Optional[str] = None             # "Remastered 2011", etc.
    copyright: Optional[str] = None

    # Audio quality
    explicit: Optional[bool] = None
    audio_quality: Optional[str] = None       # Tidal: LOSSLESS, HI_RES, etc.

    # Artwork / media
    album_art_url: Optional[str] = None
    preview_url: Optional[str] = None         # 30s preview (Beatport)
    waveform_url: Optional[str] = None        # Beatport waveform

    # Extras
    composer: Optional[str] = None            # Tidal
    lyrics_available: Optional[bool] = None   # Tidal

    # Matching
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

    # Core identity (canonical)
    canonical_title: Optional[str] = None
    canonical_artist: Optional[str] = None
    canonical_album: Optional[str] = None
    canonical_isrc: Optional[str] = None

    # Timing
    canonical_duration: Optional[float] = None
    canonical_duration_source: Optional[str] = None
    canonical_year: Optional[int] = None
    canonical_release_date: Optional[str] = None

    # DJ-essential (canonical)
    canonical_bpm: Optional[float] = None
    canonical_key: Optional[str] = None
    canonical_genre: Optional[str] = None
    canonical_sub_genre: Optional[str] = None

    # Release info
    canonical_label: Optional[str] = None
    canonical_catalog_number: Optional[str] = None
    canonical_mix_name: Optional[str] = None

    # Audio quality
    canonical_explicit: Optional[bool] = None

    # Audio features (never populated - Spotify audio features API was removed)
    canonical_energy: Optional[float] = None
    canonical_danceability: Optional[float] = None
    canonical_valence: Optional[float] = None
    canonical_acousticness: Optional[float] = None
    canonical_instrumentalness: Optional[float] = None
    canonical_loudness: Optional[float] = None

    # Media
    canonical_album_art_url: Optional[str] = None

    # Health evaluation
    metadata_health: MetadataHealth = MetadataHealth.UNKNOWN
    metadata_health_reason: Optional[str] = None

    # Match info
    enrichment_confidence: MatchConfidence = MatchConfidence.NONE
    enrichment_providers: List[str] = field(default_factory=list)

    # Provider IDs for linking
    beatport_id: Optional[str] = None
    tidal_id: Optional[str] = None

    # All provider matches (for auditing)
    matches: List[ProviderTrack] = field(default_factory=list)

    # Resolution log for debugging
    log: List[str] = field(default_factory=list)

    # V3 identity ingestion confidence hint (optional)
    ingestion_confidence: Optional[str] = None


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

    # Genre/style tags (for normalization workflows)
    tag_genre: Optional[str] = None
    tag_subgenre: Optional[str] = None
    tag_style: Optional[str] = None
    tag_genre_preferred: Optional[str] = None
    tag_genre_full: Optional[str] = None

    # Known provider IDs (if any)
    tidal_id: Optional[str] = None
    beatport_id: Optional[str] = None
    beatport_track_url: Optional[str] = None
    beatport_release_id: Optional[str] = None
    beatport_release_url: Optional[str] = None


@dataclass(slots=True)
class TidalSeedRow:
    """Stable TIDAL-only intake row for vendor enrichment flows."""

    tidal_playlist_id: str
    tidal_track_id: str
    tidal_url: str
    title: str
    artist: str
    isrc: Optional[str] = None


@dataclass(slots=True)
class TidalBeatportMergedRow:
    """Merged vendor row with TIDAL intake fields and Beatport enrichment fields."""

    tidal_playlist_id: str
    tidal_track_id: str
    tidal_url: str
    title: str
    artist: str
    isrc: Optional[str] = None
    beatport_track_id: Optional[str] = None
    beatport_release_id: Optional[str] = None
    beatport_url: Optional[str] = None
    beatport_bpm: Optional[str] = None
    beatport_key: Optional[str] = None
    beatport_genre: Optional[str] = None
    beatport_subgenre: Optional[str] = None
    beatport_label: Optional[str] = None
    beatport_catalog_number: Optional[str] = None
    beatport_upc: Optional[str] = None
    beatport_release_date: Optional[str] = None
    match_method: str = "no_match"
    match_confidence: MatchConfidence = MatchConfidence.NONE
    last_synced_at: Optional[str] = None


TIDAL_SEED_COLUMNS = (
    "tidal_playlist_id",
    "tidal_track_id",
    "tidal_url",
    "title",
    "artist",
    "isrc",
)

TIDAL_BEATPORT_MERGED_COLUMNS = (
    "tidal_playlist_id",
    "tidal_track_id",
    "tidal_url",
    "title",
    "artist",
    "isrc",
    "beatport_track_id",
    "beatport_release_id",
    "beatport_url",
    "beatport_bpm",
    "beatport_key",
    "beatport_genre",
    "beatport_subgenre",
    "beatport_label",
    "beatport_catalog_number",
    "beatport_upc",
    "beatport_release_date",
    "match_method",
    "match_confidence",
    "last_synced_at",
)


@dataclass(slots=True)
class BeatportSeedRow:
    """Stable Beatport-only intake row for vendor enrichment flows."""

    beatport_track_id: str
    beatport_release_id: Optional[str]
    beatport_url: str
    title: str
    artist: str
    isrc: Optional[str] = None
    beatport_bpm: Optional[str] = None
    beatport_key: Optional[str] = None
    beatport_genre: Optional[str] = None
    beatport_subgenre: Optional[str] = None
    beatport_label: Optional[str] = None
    beatport_catalog_number: Optional[str] = None
    beatport_upc: Optional[str] = None
    beatport_release_date: Optional[str] = None


@dataclass(slots=True)
class BeatportTidalMergedRow:
    """Merged vendor row with Beatport intake fields and TIDAL enrichment fields."""

    beatport_track_id: str
    beatport_release_id: Optional[str]
    beatport_url: str
    title: str
    artist: str
    isrc: Optional[str] = None
    beatport_bpm: Optional[str] = None
    beatport_key: Optional[str] = None
    beatport_genre: Optional[str] = None
    beatport_subgenre: Optional[str] = None
    beatport_label: Optional[str] = None
    beatport_catalog_number: Optional[str] = None
    beatport_upc: Optional[str] = None
    beatport_release_date: Optional[str] = None
    tidal_track_id: Optional[str] = None
    tidal_url: Optional[str] = None
    tidal_title: Optional[str] = None
    tidal_artist: Optional[str] = None
    match_method: str = "no_match"
    match_confidence: MatchConfidence = MatchConfidence.NONE
    last_synced_at: Optional[str] = None


BEATPORT_SEED_COLUMNS = (
    "beatport_track_id",
    "beatport_release_id",
    "beatport_url",
    "title",
    "artist",
    "isrc",
    "beatport_bpm",
    "beatport_key",
    "beatport_genre",
    "beatport_subgenre",
    "beatport_label",
    "beatport_catalog_number",
    "beatport_upc",
    "beatport_release_date",
)

BEATPORT_TIDAL_MERGED_COLUMNS = (
    "beatport_track_id",
    "beatport_release_id",
    "beatport_url",
    "title",
    "artist",
    "isrc",
    "beatport_bpm",
    "beatport_key",
    "beatport_genre",
    "beatport_subgenre",
    "beatport_label",
    "beatport_catalog_number",
    "beatport_upc",
    "beatport_release_date",
    "tidal_track_id",
    "tidal_url",
    "tidal_title",
    "tidal_artist",
    "match_method",
    "match_confidence",
    "last_synced_at",
)


@dataclass(slots=True)
class TidalSeedExportStats:
    """Telemetry for TIDAL playlist seed export."""

    playlist_id: str
    exported_rows: int = 0
    missing_isrc_rows: int = 0
    malformed_playlist_items: int = 0
    rows_missing_required_fields: int = 0
    duplicate_rows: int = 0
    pages_fetched: int = 0
    endpoint_fallback_used: int = 0
    pagination_stop_non_200: int = 0
    pagination_stop_empty_page: int = 0
    pagination_stop_repeated_next: int = 0
    pagination_stop_short_page_no_next: int = 0


@dataclass(slots=True)
class BeatportSeedExportStats:
    """Telemetry for Beatport library seed export."""

    exported_rows: int = 0
    missing_isrc_rows: int = 0
    rows_missing_required_fields: int = 0
    duplicate_rows: int = 0
    pages_fetched: int = 0
    pagination_stop_non_200: int = 0
    pagination_stop_empty_page: int = 0
    pagination_stop_short_page_no_next: int = 0


@dataclass(slots=True)
class TidalBeatportEnrichmentStats:
    """Telemetry for Beatport enrichment of a TIDAL seed CSV."""

    input_rows: int = 0
    discarded_seed_rows: int = 0
    output_rows: int = 0
    isrc_matches: int = 0
    title_artist_fallback_matches: int = 0
    no_match_rows: int = 0
    ambiguous_isrc_rows: int = 0
    ambiguous_fallback_rows: int = 0
    fallback_equal_rank_ties: int = 0


@dataclass(slots=True)
class BeatportTidalEnrichmentStats:
    """Telemetry for TIDAL enrichment of a Beatport seed CSV."""

    input_rows: int = 0
    discarded_seed_rows: int = 0
    output_rows: int = 0
    isrc_matches: int = 0
    title_artist_fallback_matches: int = 0
    no_match_rows: int = 0
    ambiguous_isrc_rows: int = 0
    ambiguous_fallback_rows: int = 0
    fallback_equal_rank_ties: int = 0
