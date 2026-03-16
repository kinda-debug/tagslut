"""
Data models for metadata enrichment.
"""

from dataclasses import dataclass, field, fields
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
    service: str                      # spotify, qobuz, tidal, beatport, itunes
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
    genre: Optional[str] = None
    sub_genre: Optional[str] = None           # Beatport sub-genre

    # Release info
    label: Optional[str] = None
    catalog_number: Optional[str] = None      # Beatport
    mix_name: Optional[str] = None            # "Original Mix", "Radio Edit", etc.
    version: Optional[str] = None             # "Remastered 2011", etc.
    copyright: Optional[str] = None

    # Audio quality
    explicit: Optional[bool] = None
    audio_quality: Optional[str] = None       # Tidal: LOSSLESS, HI_RES, etc.
    bit_depth: Optional[int] = None           # Qobuz hi-res
    sample_rate: Optional[int] = None         # Qobuz hi-res

    # Spotify audio features
    energy: Optional[float] = None            # 0.0 - 1.0
    danceability: Optional[float] = None      # 0.0 - 1.0
    valence: Optional[float] = None           # 0.0 - 1.0 (positiveness)
    acousticness: Optional[float] = None
    instrumentalness: Optional[float] = None
    liveness: Optional[float] = None
    speechiness: Optional[float] = None
    loudness: Optional[float] = None          # dB
    time_signature: Optional[int] = None
    mode: Optional[int] = None                # 0=minor, 1=major

    # Artwork / media
    album_art_url: Optional[str] = None
    preview_url: Optional[str] = None         # 30s preview (Spotify, Beatport)
    waveform_url: Optional[str] = None        # Beatport waveform

    # Extras
    popularity: Optional[int] = None          # Spotify 0-100
    composer: Optional[str] = None            # Classical / Qobuz
    lyrics_available: Optional[bool] = None   # Tidal
    booklet_url: Optional[str] = None         # Qobuz digital booklet

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

    # Spotify audio features
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
    spotify_id: Optional[str] = None
    beatport_id: Optional[str] = None
    tidal_id: Optional[str] = None
    qobuz_id: Optional[str] = None
    itunes_id: Optional[str] = None
    deezer_id: Optional[str] = None
    traxsource_id: Optional[str] = None
    musicbrainz_id: Optional[str] = None

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

    # Genre/style tags (for normalization workflows)
    tag_genre: Optional[str] = None
    tag_subgenre: Optional[str] = None
    tag_style: Optional[str] = None
    tag_genre_preferred: Optional[str] = None
    tag_genre_full: Optional[str] = None

    # Known provider IDs (if any)
    spotify_id: Optional[str] = None
    qobuz_id: Optional[str] = None
    tidal_id: Optional[str] = None
    beatport_id: Optional[str] = None
    beatport_track_url: Optional[str] = None
    beatport_release_id: Optional[str] = None
    beatport_release_url: Optional[str] = None
    apple_id: Optional[str] = None

    # Fingerprint info
    acoustid_id: Optional[str] = None
    musicbrainz_id: Optional[str] = None


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
    match_confidence: float = 0.0
    last_synced_at: Optional[str] = None


TIDAL_SEED_COLUMNS = tuple(field.name for field in fields(TidalSeedRow))
TIDAL_BEATPORT_MERGED_COLUMNS = tuple(field.name for field in fields(TidalBeatportMergedRow))
