from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional

from tagslut.metadata.models.types import EnrichmentResult, LocalFileInfo, MatchConfidence, ProviderTrack
from tagslut.metadata.pipeline import stages
from tagslut.metadata.store.db_writer import CONFIDENCE_NUMERIC, _merge_into_track_identity


@dataclass
class PassthroughRouter:
    provider_names: List[str]

    def provider_names_for(self, _capability, *, log=None):  # type: ignore[no-untyped-def]  # test stub
        _ = log
        return list(self.provider_names)


@dataclass
class FakeProvider:
    id_result: Optional[ProviderTrack] = None
    release_results: Optional[List[ProviderTrack]] = None
    isrc_results: Optional[List[ProviderTrack]] = None
    search_results: Optional[List[ProviderTrack]] = None

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        _ = track_id
        return self.id_result

    def fetch_release_tracks(self, release_id: str, slug: str | None = None) -> list[ProviderTrack]:
        _ = release_id
        _ = slug
        return list(self.release_results or [])

    def search_by_isrc(self, isrc: str) -> list[ProviderTrack]:
        _ = isrc
        return list(self.isrc_results or [])

    def search(self, query: str, limit: int = 5) -> list[ProviderTrack]:
        _ = query
        _ = limit
        return list(self.search_results or [])


def _provider_getter(providers: Dict[str, FakeProvider]):
    return lambda name: providers.get(name)


def _track(service: str, track_id: str, *, title: str = "Track", artist: str = "Artist") -> ProviderTrack:
    return ProviderTrack(
        service=service,
        service_track_id=track_id,
        title=title,
        artist=artist,
    )


def test_resolve_file_stage0_beatport_track_id_match() -> None:
    beatport_track = _track("beatport", "123", title="My Track", artist="DJ X")
    providers = {"beatport": FakeProvider(id_result=beatport_track)}

    info = LocalFileInfo(path="/music/a.flac", beatport_id="123")
    result = stages.resolve_file(
        info,
        ["beatport"],
        _provider_getter(providers),
        mode="recovery",
        router=PassthroughRouter(["beatport"]),
    )

    assert len(result.matches) == 1
    assert result.matches[0].service == "beatport"
    assert result.matches[0].match_confidence == MatchConfidence.EXACT


def test_resolve_file_stage0b_release_id_title_matching() -> None:
    release_tracks = [
        _track("beatport", "r1", title="Another Track", artist="DJ X"),
        _track("beatport", "r2", title="My Song", artist="DJ Y"),
    ]
    providers = {"beatport": FakeProvider(release_results=release_tracks)}
    info = LocalFileInfo(
        path="/music/b.flac",
        beatport_release_id="999",
        tag_title="My Song (Original Mix)",
    )

    result = stages.resolve_file(
        info,
        ["beatport"],
        _provider_getter(providers),
        mode="recovery",
        router=PassthroughRouter(["beatport"]),
    )

    assert len(result.matches) == 1
    assert result.matches[0].service_track_id == "r2"
    assert result.matches[0].match_confidence == MatchConfidence.EXACT


def test_resolve_file_stage1_isrc_across_providers() -> None:
    bp = _track("beatport", "bp1")
    td = _track("tidal", "td1")
    providers = {
        "beatport": FakeProvider(isrc_results=[bp]),
        "tidal": FakeProvider(isrc_results=[td]),
    }
    info = LocalFileInfo(path="/music/c.flac", tag_isrc="USABC1234567")

    result = stages.resolve_file(
        info,
        ["beatport", "tidal"],
        _provider_getter(providers),
        mode="recovery",
        router=PassthroughRouter(["beatport", "tidal"]),
    )

    services = {m.service for m in result.matches}
    assert services == {"beatport", "tidal"}


def test_resolve_file_stage2_text_search_fallback(monkeypatch) -> None:
    providers = {"deezer": FakeProvider(search_results=[_track("deezer", "dz1")])}
    info = LocalFileInfo(path="/music/d.flac", tag_artist="Artist", tag_title="Track", measured_duration_s=240.0)
    monkeypatch.setattr(stages, "classify_match_confidence", lambda *args, **kwargs: MatchConfidence.STRONG)

    result = stages.resolve_file(
        info,
        ["deezer"],
        _provider_getter(providers),
        mode="recovery",
        router=PassthroughRouter(["deezer"]),
    )

    assert len(result.matches) == 1
    assert result.matches[0].service == "deezer"
    assert result.matches[0].match_confidence == MatchConfidence.STRONG


def test_resolve_file_stage3_title_only_fallback(monkeypatch) -> None:
    providers = {"traxsource": FakeProvider(search_results=[_track("traxsource", "tx1", title="Track")])}
    info = LocalFileInfo(path="/music/e.flac", tag_title="Track", measured_duration_s=240.0)
    monkeypatch.setattr(stages, "classify_match_confidence", lambda *args, **kwargs: MatchConfidence.MEDIUM)

    result = stages.resolve_file(
        info,
        ["traxsource"],
        _provider_getter(providers),
        mode="recovery",
        router=PassthroughRouter(["traxsource"]),
    )

    assert len(result.matches) == 1
    assert result.matches[0].service_track_id == "tx1"


def test_classify_health_ok_truncated_extended_and_edge() -> None:
    ok, _ = stages.classify_health(100.0, 99.0, tolerance=2.0)
    truncated, _ = stages.classify_health(95.0, 100.0, tolerance=2.0)
    extended, _ = stages.classify_health(105.0, 100.0, tolerance=2.0)
    edge, _ = stages.classify_health(102.0, 100.0, tolerance=2.0)

    assert ok.value == "ok"
    assert truncated.value == "suspect_truncated"
    assert extended.value == "suspect_extended"
    assert edge.value == "ok"


def test_normalize_title_strips_original_mix_suffixes() -> None:
    assert stages.normalize_title("My Song (Original Mix)") == "my song"
    assert stages.normalize_title("My Song (Main Mix)") == "my song"


def test_confidence_ordering() -> None:
    levels = ["exact", "strong", "medium", "weak", "none"]
    scores = [CONFIDENCE_NUMERIC[level] for level in levels]

    assert scores == sorted(scores, reverse=True)
    assert len(set(scores)) == len(scores)


def test_merge_into_track_identity_fills_blank_v3_fields_without_overwrite() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE asset_file (id INTEGER PRIMARY KEY, path TEXT NOT NULL)")
    conn.execute(
        """
        CREATE TABLE asset_link (
            id INTEGER PRIMARY KEY,
            asset_id INTEGER NOT NULL,
            identity_id INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE track_identity (
            id INTEGER PRIMARY KEY,
            identity_key TEXT,
            canonical_title TEXT,
            canonical_artist TEXT,
            canonical_album TEXT,
            isrc TEXT,
            canonical_label TEXT,
            canonical_catalog_number TEXT,
            canonical_mix_name TEXT,
            canonical_year INTEGER,
            canonical_release_date TEXT,
            canonical_bpm REAL,
            canonical_key TEXT,
            canonical_genre TEXT,
            canonical_sub_genre TEXT,
            beatport_id TEXT,
            tidal_id TEXT,
            canonical_duration REAL,
            duration_ref_ms INTEGER,
            ref_source TEXT,
            enriched_at TEXT,
            updated_at TEXT,
            merged_into_id INTEGER
        )
        """
    )
    conn.execute("INSERT INTO asset_file (id, path) VALUES (1, ?)", ("/music/linked.flac",))
    conn.execute(
        """
        INSERT INTO track_identity (
            id,
            identity_key,
            canonical_title,
            canonical_artist
        ) VALUES (7, 'identity:key', 'Existing Title', 'Existing Artist')
        """
    )
    conn.execute("INSERT INTO asset_link (asset_id, identity_id, active) VALUES (1, 7, 1)")

    result = EnrichmentResult(
        path="/music/linked.flac",
        canonical_title="New Title",
        canonical_artist="New Artist",
        canonical_album="Album",
        canonical_label="Hot Creations",
        canonical_catalog_number="HOTC275",
        canonical_release_date="2026-02-27",
        canonical_bpm=131.0,
        canonical_key="Ab",
        canonical_genre="Tech House",
        canonical_duration=360.0,
        beatport_id="12345",
        tidal_id="67890",
        enrichment_providers=["beatport", "tidal"],
    )
    best = ProviderTrack(
        service="beatport",
        service_track_id="12345",
        match_confidence=MatchConfidence.EXACT,
    )

    _merge_into_track_identity(conn, result, best)

    row = conn.execute(
        """
        SELECT
            canonical_title,
            canonical_artist,
            canonical_label,
            canonical_catalog_number,
            canonical_release_date,
            canonical_bpm,
            canonical_key,
            canonical_genre,
            beatport_id,
            tidal_id,
            canonical_duration,
            duration_ref_ms,
            ref_source,
            enriched_at,
            updated_at
        FROM track_identity
        WHERE id = 7
        """
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "Existing Title"
    assert row[1] == "Existing Artist"
    assert row[2] == "Hot Creations"
    assert row[3] == "HOTC275"
    assert row[4] == "2026-02-27"
    assert row[5] == 131.0
    assert row[6] == "Ab"
    assert row[7] == "Tech House"
    assert row[8] == "12345"
    assert row[9] == "67890"
    assert row[10] == 360.0
    assert row[11] == 360000
    assert row[12] == "beatport"
    assert row[13] is not None
    assert row[14] is not None
