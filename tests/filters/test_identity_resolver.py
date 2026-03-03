from __future__ import annotations

import sqlite3

import pytest

from tagslut.filters.identity_resolver import (
    DURATION_TOLERANCE_S,
    FUZZY_THRESHOLD,
    IdentityResolver,
    TrackIntent,
)
from tagslut.storage.schema import init_db


@pytest.fixture
def mem_db() -> sqlite3.Connection:
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
    quality_rank: int | None,
    canonical_isrc: str | None = None,
    isrc: str | None = None,
    beatport_id: str | None = None,
    canonical_artist: str | None = None,
    canonical_title: str | None = None,
    duration: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO files (
            path, checksum, metadata_json, quality_rank,
            canonical_isrc, isrc, beatport_id,
            canonical_artist, canonical_title, duration
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            path,
            checksum,
            "{}",
            quality_rank,
            canonical_isrc,
            isrc or canonical_isrc,
            beatport_id,
            canonical_artist,
            canonical_title,
            duration,
        ),
    )
    conn.commit()


def test_identity_constants_are_expected() -> None:
    assert FUZZY_THRESHOLD == 88
    assert DURATION_TOLERANCE_S == 2.0


def test_resolve_isrc_exact_match_returns_existing_path(mem_db: sqlite3.Connection) -> None:
    _insert_file(
        mem_db,
        path="/music/isrc.flac",
        checksum="a1",
        quality_rank=5,
        isrc="USABC1234567",
    )

    result = IdentityResolver(mem_db).resolve(
        TrackIntent(isrc="USABC1234567"), candidate_rank=3
    )

    assert result.match_method == "isrc"
    assert result.existing_path == "/music/isrc.flac"
    assert result.match_score == 100.0


def test_resolve_beatport_id_match_returns_existing_path(mem_db: sqlite3.Connection) -> None:
    _insert_file(
        mem_db,
        path="/music/beatport.flac",
        checksum="b1",
        quality_rank=5,
        beatport_id="BP-42",
    )

    result = IdentityResolver(mem_db).resolve(
        TrackIntent(beatport_id="BP-42"), candidate_rank=3
    )

    assert result.match_method == "beatport_id"
    assert result.existing_path == "/music/beatport.flac"


def test_resolve_fuzzy_match_within_duration_tolerance(mem_db: sqlite3.Connection) -> None:
    _insert_file(
        mem_db,
        path="/music/fuzzy.flac",
        checksum="f1",
        quality_rank=4,
        canonical_artist="Daft Punk",
        canonical_title="Harder Better Faster Stronger",
        duration=224.0,
    )

    result = IdentityResolver(mem_db).resolve(
        TrackIntent(
            artist="Daft Punk",
            title="Harder Better Faster Stronger",
            duration_s=225.5,
        ),
        candidate_rank=4,
    )

    assert result.match_method == "fuzzy"
    assert result.match_score is not None and result.match_score >= FUZZY_THRESHOLD


def test_resolve_no_match_returns_new(mem_db: sqlite3.Connection) -> None:
    result = IdentityResolver(mem_db).resolve(
        TrackIntent(title="Unknown", artist="Nobody", isrc="NOPE"),
        candidate_rank=4,
    )

    assert result.action == "new"
    assert result.existing_path is None


def test_resolve_quality_upgrade_when_candidate_is_better(mem_db: sqlite3.Connection) -> None:
    _insert_file(
        mem_db,
        path="/music/upgrade.flac",
        checksum="u1",
        quality_rank=5,
        isrc="USUPGRADE123",
    )

    result = IdentityResolver(mem_db).resolve(
        TrackIntent(isrc="USUPGRADE123"), candidate_rank=2
    )

    assert result.action == "upgrade"
    assert result.existing_quality_rank == 5
    assert result.candidate_quality_rank == 2


def test_resolve_quality_skip_when_candidate_not_better(mem_db: sqlite3.Connection) -> None:
    _insert_file(
        mem_db,
        path="/music/skip.flac",
        checksum="s1",
        quality_rank=2,
        isrc="USSKIP123",
    )

    result = IdentityResolver(mem_db).resolve(
        TrackIntent(isrc="USSKIP123"), candidate_rank=2
    )

    assert result.action == "skip"


def test_resolve_fuzzy_rejects_outside_duration_tolerance(mem_db: sqlite3.Connection) -> None:
    _insert_file(
        mem_db,
        path="/music/fuzzy_out.flac",
        checksum="fo1",
        quality_rank=3,
        canonical_artist="Nina Kraviz",
        canonical_title="Ghetto Kraviz",
        duration=360.0,
    )

    result = IdentityResolver(mem_db).resolve(
        TrackIntent(artist="Nina Kraviz", title="Ghetto Kraviz", duration_s=365.0),
        candidate_rank=1,
    )

    assert result.action == "new"
    assert result.match_method is None
