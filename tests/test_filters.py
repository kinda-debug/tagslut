import sqlite3

import pytest

from tagslut.filters.gig_filter import FilterParseError, parse_filter
from tagslut.filters.identity_resolver import IdentityResolver, TrackIntent
from tagslut.filters.macos_filters import MacOSFilters
from tagslut.storage.schema import init_db


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def _insert_file(
    conn: sqlite3.Connection,
    *,
    path: str,
    checksum: str,
    quality_rank: int | None = None,
    canonical_isrc: str | None = None,
    beatport_id: str | None = None,
    tidal_id: str | None = None,
    qobuz_id: str | None = None,
    canonical_artist: str | None = None,
    canonical_title: str | None = None,
    duration: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO files (
            path, checksum, metadata_json, quality_rank,
            canonical_isrc, beatport_id, tidal_id, qobuz_id,
            canonical_artist, canonical_title, duration
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            path,
            checksum,
            "{}",
            quality_rank,
            canonical_isrc,
            beatport_id,
            tidal_id,
            qobuz_id,
            canonical_artist,
            canonical_title,
            duration,
        ),
    )
    conn.commit()


def test_parse_filter_empty():
    assert parse_filter("") == ("1=1", [])
    assert parse_filter("   ") == ("1=1", [])


def test_parse_filter_plain_equality():
    clause, params = parse_filter("genre:techno")
    assert clause == "canonical_genre = ?"
    assert params == ["techno"]


def test_parse_filter_range_comparison_boolean_multivalue_date():
    clause, params = parse_filter(
        "bpm:128-145 quality_rank:<=3 dj_flag:true key:8A,9A added:>2025-01-01"
    )
    assert clause == (
        "canonical_bpm BETWEEN ? AND ? AND quality_rank <= ? AND is_dj_material = ? "
        "AND canonical_key IN (?,?) AND download_date > ?"
    )
    assert params == [128.0, 145.0, 3.0, 1, "8A", "9A", "2025-01-01"]


def test_parse_filter_boolean_false_and_numeric_equals():
    clause, params = parse_filter("dj_flag:false quality_rank:=4")
    assert clause == "is_dj_material = ? AND quality_rank = ?"
    assert params == [0, 4.0]


def test_parse_filter_invalid_missing_colon():
    with pytest.raises(FilterParseError):
        parse_filter("genre")


def test_parse_filter_unknown_key():
    with pytest.raises(FilterParseError):
        parse_filter("unknown:value")


def test_identity_resolver_new_when_no_match(mem_db):
    resolver = IdentityResolver(mem_db)
    result = resolver.resolve(TrackIntent(isrc="NOPE"), candidate_rank=4)
    assert result.action == "new"
    assert result.existing_path is None


def test_identity_resolver_isrc_match_upgrade(mem_db):
    _insert_file(
        mem_db,
        path="/music/a.flac",
        checksum="a",
        quality_rank=5,
        canonical_isrc="USABC1234567",
    )
    resolver = IdentityResolver(mem_db)
    result = resolver.resolve(TrackIntent(isrc="USABC1234567"), candidate_rank=3)
    assert result.action == "upgrade"
    assert result.match_method == "isrc"
    assert result.match_score == 100.0


def test_identity_resolver_isrc_match_skip(mem_db):
    _insert_file(
        mem_db,
        path="/music/a.flac",
        checksum="a",
        quality_rank=2,
        canonical_isrc="USABC1234567",
    )
    resolver = IdentityResolver(mem_db)
    result = resolver.resolve(TrackIntent(isrc="USABC1234567"), candidate_rank=4)
    assert result.action == "skip"


def test_identity_resolver_priority_beatport_tidal_qobuz(mem_db):
    _insert_file(mem_db, path="/m/bp.flac", checksum="bp", quality_rank=4, beatport_id="BP1")
    _insert_file(mem_db, path="/m/ti.flac", checksum="ti", quality_rank=4, tidal_id="TI1")
    _insert_file(mem_db, path="/m/qb.flac", checksum="qb", quality_rank=4, qobuz_id="QB1")

    resolver = IdentityResolver(mem_db)

    bp = resolver.resolve(TrackIntent(beatport_id="BP1"), candidate_rank=4)
    ti = resolver.resolve(TrackIntent(tidal_id="TI1"), candidate_rank=4)
    qb = resolver.resolve(TrackIntent(qobuz_id="QB1"), candidate_rank=4)

    assert bp.match_method == "beatport_id"
    assert ti.match_method == "tidal_id"
    assert qb.match_method == "qobuz_id"


def test_identity_resolver_fuzzy_match_with_duration_gate(mem_db):
    _insert_file(
        mem_db,
        path="/music/fuzzy.flac",
        checksum="f",
        quality_rank=4,
        canonical_artist="Test Artist",
        canonical_title="Great Track",
        duration=240.0,
    )
    resolver = IdentityResolver(mem_db)

    # Within tolerance -> fuzzy hit
    ok = resolver.resolve(
        TrackIntent(artist="Test Artist", title="Great Track", duration_s=241.0),
        candidate_rank=4,
    )
    assert ok.match_method == "fuzzy"

    # Outside tolerance -> no fuzzy hit
    miss = resolver.resolve(
        TrackIntent(artist="Test Artist", title="Great Track", duration_s=260.5),
        candidate_rank=4,
    )
    assert miss.action == "new"


def test_identity_resolver_ignores_rows_without_quality_rank(mem_db):
    _insert_file(
        mem_db,
        path="/music/no-rank.flac",
        checksum="n",
        quality_rank=None,
        canonical_isrc="USABC1234567",
    )
    resolver = IdentityResolver(mem_db)
    result = resolver.resolve(TrackIntent(isrc="USABC1234567"), candidate_rank=4)
    assert result.action == "new"


def test_macos_filters_is_metadata():
    assert MacOSFilters.is_macos_metadata("/tmp/._track.flac") is True
    assert MacOSFilters.is_macos_metadata("/tmp/.DS_Store") is True
    assert MacOSFilters.is_macos_metadata("/tmp/track.flac") is False


def test_macos_filters_filter_and_count():
    files = [
        "/music/._hidden",
        "/music/.DS_Store",
        "/music/track1.flac",
        "/music/track2.mp3",
    ]
    filtered = MacOSFilters.filter_files(files)
    counts = MacOSFilters.count_filtered(files)

    assert filtered == ["/music/track1.flac", "/music/track2.mp3"]
    assert counts == {"total": 4, "kept": 2, "removed": 2}
