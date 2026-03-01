"""Smoke tests for the tagslut.metadata submodule."""

import tagslut.metadata as metadata_mod
from tagslut.metadata import EnrichmentResult, ProviderTrack
from tagslut.metadata.models.types import MatchConfidence, MetadataHealth


def test_metadata_module_importable() -> None:
    assert hasattr(metadata_mod, "ProviderTrack")
    assert hasattr(metadata_mod, "EnrichmentResult")
    assert hasattr(metadata_mod, "TokenManager")


def test_provider_track_instantiates_with_minimal_input() -> None:
    track = ProviderTrack(service="spotify", service_track_id="abc123")
    assert track.service == "spotify"
    assert track.service_track_id == "abc123"
    assert track.match_confidence == MatchConfidence.NONE


def test_provider_track_duration_s_converts_ms() -> None:
    track = ProviderTrack(service="tidal", service_track_id="t1", duration_ms=180000)
    assert track.duration_s == 180.0


def test_provider_track_duration_s_none_when_unset() -> None:
    track = ProviderTrack(service="qobuz", service_track_id="q1")
    assert track.duration_s is None


def test_enrichment_result_instantiates_with_path() -> None:
    result = EnrichmentResult(path="/music/track.flac")
    assert result.path == "/music/track.flac"
    assert result.metadata_health == MetadataHealth.UNKNOWN
    assert result.enrichment_providers == []
    assert result.matches == []


def test_enrichment_result_accepts_canonical_fields() -> None:
    result = EnrichmentResult(
        path="/music/track.flac",
        canonical_title="My Track",
        canonical_artist="DJ Test",
        canonical_bpm=128.0,
    )
    assert result.canonical_title == "My Track"
    assert result.canonical_bpm == 128.0
