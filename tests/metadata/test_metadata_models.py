from __future__ import annotations

from tagslut.metadata.models.precedence import (
    ALBUM_PRECEDENCE,
    ARTIST_PRECEDENCE,
    AUDIO_FEATURES_SOURCE,
    BPM_PRECEDENCE,
    KEY_PRECEDENCE,
)
from tagslut.metadata.models.types import (
    EnrichmentResult,
    LocalFileInfo,
    MatchConfidence,
    MetadataHealth,
    ProviderTrack,
)


def test_match_confidence_enum_values() -> None:
    assert MatchConfidence.EXACT.value == "exact"
    assert MatchConfidence.STRONG.value == "strong"
    assert MatchConfidence.MEDIUM.value == "medium"
    assert MatchConfidence.WEAK.value == "weak"
    assert MatchConfidence.NONE.value == "none"


def test_metadata_health_enum_values() -> None:
    assert MetadataHealth.OK.value == "ok"
    assert MetadataHealth.SUSPECT_TRUNCATED.value == "suspect_truncated"
    assert MetadataHealth.SUSPECT_EXTENDED.value == "suspect_extended"
    assert MetadataHealth.UNKNOWN.value == "unknown"


def test_provider_track_minimal_construction() -> None:
    track = ProviderTrack(service="spotify", service_track_id="sp-1")

    assert track.service == "spotify"
    assert track.service_track_id == "sp-1"
    assert track.match_confidence == MatchConfidence.NONE


def test_provider_track_duration_seconds_conversion() -> None:
    track = ProviderTrack(service="tidal", service_track_id="td-1", duration_ms=123000)
    assert track.duration_s == 123.0


def test_enrichment_result_construction_defaults() -> None:
    result = EnrichmentResult(path="/music/a.flac")

    assert result.path == "/music/a.flac"
    assert result.metadata_health == MetadataHealth.UNKNOWN
    assert result.enrichment_providers == []
    assert result.matches == []


def test_local_file_info_construction() -> None:
    local = LocalFileInfo(
        path="/library/track.flac",
        measured_duration_s=312.7,
        tag_artist="Artist",
        tag_title="Track",
        tag_genre="Tech House",
    )

    assert local.path.endswith("track.flac")
    assert local.measured_duration_s == 312.7
    assert local.tag_genre == "Tech House"


def test_precedence_lists_include_expected_services() -> None:
    assert "beatport" in BPM_PRECEDENCE
    assert "beatport" in KEY_PRECEDENCE
    assert ARTIST_PRECEDENCE[0] == "tidal"
    assert "itunes" not in ALBUM_PRECEDENCE
    assert AUDIO_FEATURES_SOURCE == ""
