"""Tests for the enrichment pipeline cascade logic.

Covers:
- resolve_file hoarding gap-fill (Stage 4)
- apply_cascade precedence selection
- Provider ID extraction
"""

from tagslut.metadata.models.types import (
    EnrichmentResult,
    LocalFileInfo,
    MatchConfidence,
    ProviderTrack,
)
from tagslut.metadata.pipeline.stages import resolve_file, apply_cascade


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_track(
    service: str,
    *,
    title: str = "Around The World",
    artist: str = "Daft Punk",
    bpm: float | None = None,
    key: str | None = None,
    genre: str | None = None,
    isrc: str | None = None,
    duration_ms: int | None = 240_000,
    confidence: MatchConfidence = MatchConfidence.EXACT,
    track_id: str = "12345",
) -> ProviderTrack:
    return ProviderTrack(
        service=service,
        service_track_id=track_id,
        title=title,
        artist=artist,
        bpm=bpm,
        key=key,
        genre=genre,
        isrc=isrc,
        duration_ms=duration_ms,
        match_confidence=confidence,
    )


def _make_file_info(
    *,
    path: str = "/music/test.flac",
    tag_artist: str | None = "Daft Punk",
    tag_title: str | None = "Around The World",
    tag_isrc: str | None = None,
    measured_duration_s: float | None = 240.0,
    beatport_id: str | None = None,
) -> LocalFileInfo:
    return LocalFileInfo(
        path=path,
        tag_artist=tag_artist,
        tag_title=tag_title,
        tag_isrc=tag_isrc,
        measured_duration_s=measured_duration_s,
        beatport_id=beatport_id,
    )


class FakeProvider:
    """Minimal mock provider that returns pre-configured results."""

    def __init__(
        self,
        name: str,
        *,
        isrc_results: list[ProviderTrack] | None = None,
        search_results: list[ProviderTrack] | None = None,
        id_result: ProviderTrack | None = None,
    ):
        self.name = name
        self._isrc_results = isrc_results or []
        self._search_results = search_results or []
        self._id_result = id_result
        self.search_calls: list[str] = []
        self.isrc_calls: list[str] = []

    def search_by_isrc(self, isrc: str) -> list[ProviderTrack]:
        self.isrc_calls.append(isrc)
        return self._isrc_results

    def search(self, query: str, limit: int = 5) -> list[ProviderTrack]:
        self.search_calls.append(query)
        return self._search_results

    def fetch_by_id(self, track_id: str) -> ProviderTrack | None:
        return self._id_result


def _make_provider_getter(providers: dict[str, FakeProvider]):
    """Return a provider_getter function for resolve_file."""
    def getter(name: str):
        return providers.get(name)
    return getter


# ===========================================================================
# Tests: resolve_file hoarding gap-fill (Stage 4)
# ===========================================================================

class TestHoardingGapFill:
    """Stage 4 should search providers that didn't match in earlier stages."""

    def test_gap_fill_searches_missing_providers(self):
        """When ISRC matches Beatport but not Tidal, hoarding gap-fill
        should text-search Tidal to get additional metadata."""
        bp_track = _make_track("beatport", bpm=128.0, key=None, genre="Techno")
        tidal_track = _make_track(
            "tidal", bpm=128.0, key="F# minor", genre="Electronic",
            track_id="T999",
            confidence=MatchConfidence.STRONG,
        )

        providers = {
            "beatport": FakeProvider("beatport", isrc_results=[bp_track]),
            "tidal": FakeProvider("tidal", isrc_results=[], search_results=[tidal_track]),
        }

        file_info = _make_file_info(tag_isrc="USRC12345678")
        result = resolve_file(
            file_info,
            ["beatport", "tidal"],
            _make_provider_getter(providers),
            mode="hoarding",
        )

        # Tidal should have been text-searched in gap-fill
        assert len(providers["tidal"].search_calls) == 1
        # Both providers should have matches
        services = {m.service for m in result.matches}
        assert "beatport" in services
        assert "tidal" in services

    def test_gap_fill_skipped_in_recovery_mode(self):
        """Recovery mode should NOT trigger gap-fill stage."""
        bp_track = _make_track("beatport", bpm=128.0)
        tidal_track = _make_track("tidal", key="A minor")

        providers = {
            "beatport": FakeProvider("beatport", isrc_results=[bp_track]),
            "tidal": FakeProvider("tidal", isrc_results=[], search_results=[tidal_track]),
        }

        file_info = _make_file_info(tag_isrc="USRC12345678")
        resolve_file(
            file_info,
            ["beatport", "tidal"],
            _make_provider_getter(providers),
            mode="recovery",
        )

        # Tidal should NOT have been text-searched
        assert len(providers["tidal"].search_calls) == 0

    def test_gap_fill_skips_already_matched_providers(self):
        """Providers that already matched via ISRC should not be re-searched."""
        bp_track = _make_track("beatport", bpm=128.0)
        tidal_track = _make_track("tidal", key="A minor")

        providers = {
            "beatport": FakeProvider("beatport", isrc_results=[bp_track]),
            "tidal": FakeProvider("tidal", isrc_results=[tidal_track]),
        }

        file_info = _make_file_info(tag_isrc="USRC12345678")
        resolve_file(
            file_info,
            ["beatport", "tidal"],
            _make_provider_getter(providers),
            mode="hoarding",
        )

        # Both matched via ISRC, no gap-fill search needed
        assert len(providers["beatport"].search_calls) == 0
        assert len(providers["tidal"].search_calls) == 0

    def test_gap_fill_no_artist_title_skips(self):
        """Gap-fill requires artist+title; skip if missing."""
        bp_track = _make_track("beatport", bpm=128.0)

        providers = {
            "beatport": FakeProvider("beatport", isrc_results=[bp_track]),
            "tidal": FakeProvider("tidal", isrc_results=[], search_results=[]),
        }

        file_info = _make_file_info(tag_isrc="USRC12345678", tag_artist=None, tag_title=None)
        resolve_file(
            file_info,
            ["beatport", "tidal"],
            _make_provider_getter(providers),
            mode="hoarding",
        )

        # No text search without artist+title
        assert len(providers["tidal"].search_calls) == 0

    def test_gap_fill_in_both_mode(self):
        """Both mode should trigger gap-fill."""
        bp_track = _make_track("beatport", bpm=128.0)
        tidal_track = _make_track(
            "tidal", key="D minor",
            confidence=MatchConfidence.STRONG,
        )

        providers = {
            "beatport": FakeProvider("beatport", isrc_results=[bp_track]),
            "tidal": FakeProvider("tidal", isrc_results=[], search_results=[tidal_track]),
        }

        file_info = _make_file_info(tag_isrc="USRC12345678")
        result = resolve_file(
            file_info,
            ["beatport", "tidal"],
            _make_provider_getter(providers),
            mode="both",
        )

        assert len(providers["tidal"].search_calls) == 1
        services = {m.service for m in result.matches}
        assert "tidal" in services


# ===========================================================================
# Tests: apply_cascade precedence
# ===========================================================================

class TestApplyCascade:

    def test_key_fallback_from_tidal(self):
        """If Beatport has no key, Tidal key should be used via precedence."""
        bp_track = _make_track("beatport", bpm=128.0, key=None, genre="Techno")
        tidal_track = _make_track(
            "tidal", bpm=127.5, key="F# minor", genre="Electronic",
            confidence=MatchConfidence.STRONG,
        )

        file_info = _make_file_info()
        result = EnrichmentResult(path=file_info.path)
        result.matches = [bp_track, tidal_track]

        result = apply_cascade(result, file_info, mode="hoarding")

        # BPM from Beatport (precedence), key from Tidal (fallback)
        assert result.canonical_bpm == 128.0
        assert result.canonical_key == "F# minor"
        assert result.canonical_genre == "Techno"

    def test_bpm_fallback_from_tidal(self):
        """If Beatport has no BPM, Tidal should fill in."""
        bp_track = _make_track("beatport", bpm=None, genre="Deep House")
        tidal_track = _make_track(
            "tidal", bpm=122.0, genre="Deep House",
            confidence=MatchConfidence.STRONG,
        )

        file_info = _make_file_info()
        result = EnrichmentResult(path=file_info.path)
        result.matches = [bp_track, tidal_track]

        result = apply_cascade(result, file_info, mode="hoarding")
        assert result.canonical_bpm == 122.0

    def test_key_fallback_from_tidal(self):
        """Tidal key should fill when Beatport lacks it."""
        tidal_track = _make_track(
            "tidal", bpm=123.0, key="Bb minor", genre="House",
            confidence=MatchConfidence.EXACT,
        )

        file_info = _make_file_info()
        result = EnrichmentResult(path=file_info.path)
        result.matches = [tidal_track]

        result = apply_cascade(result, file_info, mode="hoarding")
        assert result.canonical_key == "Bb minor"
        assert result.canonical_bpm == 123.0


# ===========================================================================
# Tests: Provider ID extraction
# ===========================================================================

class TestProviderIds:

    def test_beatport_id_stored(self):
        track = _make_track("beatport", track_id="BP999")
        file_info = _make_file_info()
        result = EnrichmentResult(path=file_info.path)
        result.matches = [track]

        result = apply_cascade(result, file_info, mode="hoarding")
        assert result.beatport_id == "BP999"

    def test_tidal_id_stored(self):
        track = _make_track("tidal", track_id="TI888")
        file_info = _make_file_info()
        result = EnrichmentResult(path=file_info.path)
        result.matches = [track]

        result = apply_cascade(result, file_info, mode="hoarding")
        assert result.tidal_id == "TI888"

    def test_all_provider_ids_from_multi_match(self):
        """Multiple matches should populate all provider IDs."""
        bp = _make_track("beatport", track_id="BP1")
        tidal = _make_track("tidal", track_id="TI2", confidence=MatchConfidence.STRONG)

        file_info = _make_file_info()
        result = EnrichmentResult(path=file_info.path)
        result.matches = [bp, tidal]

        result = apply_cascade(result, file_info, mode="hoarding")
        assert result.beatport_id == "BP1"
        assert result.tidal_id == "TI2"

    def test_empty_track_id_not_stored(self):
        """Provider ID should not be stored if service_track_id is empty."""
        track = _make_track("beatport", track_id="")
        file_info = _make_file_info()
        result = EnrichmentResult(path=file_info.path)
        result.matches = [track]

        result = apply_cascade(result, file_info, mode="hoarding")
        assert result.beatport_id is None


# ===========================================================================
# Tests: Precedence list sanity
# ===========================================================================

class TestPrecedenceLists:

    def test_key_precedence_includes_tidal(self):
        from tagslut.metadata.models.precedence import KEY_PRECEDENCE
        assert "tidal" in KEY_PRECEDENCE
        assert "beatport" in KEY_PRECEDENCE

    def test_bpm_precedence_beatport_first(self):
        from tagslut.metadata.models.precedence import BPM_PRECEDENCE
        assert "beatport" == BPM_PRECEDENCE[0]
        assert "tidal" in BPM_PRECEDENCE

    def test_genre_precedence_includes_tidal(self):
        from tagslut.metadata.models.precedence import GENRE_PRECEDENCE
        assert "tidal" in GENRE_PRECEDENCE

    def test_isrc_precedence_includes_providers(self):
        from tagslut.metadata.models.precedence import ISRC_PRECEDENCE
        assert "beatport" in ISRC_PRECEDENCE
        assert "tidal" in ISRC_PRECEDENCE
