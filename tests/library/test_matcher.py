from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from tagslut.adapters.rekordbox import importer as importer_module
from tagslut.adapters.rekordbox.importer import import_rekordbox_xml
from tagslut.library import create_library_engine, ensure_library_schema
from tagslut.library.matcher import MIN_SCORE_THRESHOLD, TrackMatcher, TrackQuery
from tagslut.library.models import Track, TrackAlias, TrackFile
from tagslut.library.repositories import upsert_track, upsert_track_alias, upsert_track_file
from tagslut.utils.config import _clear_config_instance

FIXTURE_XML = Path(__file__).resolve().parent / "fixtures" / "small_rekordbox.xml"


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'matcher.db').resolve()}"


def _seed_track(
    session: Session,
    *,
    title: str,
    artist: str,
    duration_ms: int | None = None,
    mix_name: str | None = None,
) -> Track:
    track = upsert_track(
        session,
        Track(
            canonical_title=title,
            sort_title=title.casefold(),
            canonical_artist_credit=artist,
            sort_artist_credit=artist.casefold(),
            canonical_mix_name=mix_name,
            status="active",
        ),
    )
    if duration_ms is not None:
        upsert_track_file(
            session,
            TrackFile(
                track_id=track.id,
                path=f"/tmp/{track.id}.mp3",
                duration_ms=duration_ms,
                role="dj_derivative",
                is_preferred=True,
                active=True,
            ),
        )
    return track


def test_exact_external_id_match(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)
    ensure_library_schema(db_url)
    engine = create_library_engine(db_url)

    with Session(engine) as session:
        track = _seed_track(session, title="Alpha Anthem", artist="DJ Exact")
        upsert_track_alias(
            session,
            TrackAlias(
                track_id=track.id,
                alias_type="rekordbox_track_id",
                value="rb-123",
                provider="rekordbox",
                source="test",
                confidence=1.0,
            ),
        )
        session.commit()

        result = TrackMatcher(session).match(
            TrackQuery(title="ignored", artist="ignored", rekordbox_id="rb-123")
        )

    assert result.track is not None
    assert result.track.id == track.id
    assert result.score == 1.0
    assert result.alias_hit is True


def test_normalized_title_artist_match(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)
    ensure_library_schema(db_url)
    engine = create_library_engine(db_url)

    with Session(engine) as session:
        track = _seed_track(
            session,
            title="Hello, World!",
            artist="DJ Test",
            duration_ms=180000,
        )
        session.commit()

        result = TrackMatcher(session).match(
            TrackQuery(title="hello world", artist="dj   test", duration_ms=180000)
        )

    assert result.track is not None
    assert result.track.id == track.id
    assert result.score >= MIN_SCORE_THRESHOLD


def test_duration_tolerance_primary(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)
    ensure_library_schema(db_url)
    engine = create_library_engine(db_url)

    with Session(engine) as session:
        track = _seed_track(
            session,
            title="Tolerance Track",
            artist="Window Artist",
            duration_ms=200000,
        )
        session.commit()

        result = TrackMatcher(session).match(
            TrackQuery(title="Tolerance Track", artist="Window Artist", duration_ms=201900)
        )

    assert result.track is not None
    assert result.track.id == track.id
    assert result.score >= MIN_SCORE_THRESHOLD
    assert any("primary tolerance" in reason for reason in result.reasons)


def test_duration_tolerance_fallback(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)
    ensure_library_schema(db_url)
    engine = create_library_engine(db_url)

    with Session(engine) as session:
        track = _seed_track(
            session,
            title="Fallback Track",
            artist="Window Artist",
            duration_ms=200000,
        )
        session.commit()

        result = TrackMatcher(session).match(
            TrackQuery(title="Fallback Track", artist="Window Artist", duration_ms=204000)
        )

    assert result.track is not None
    assert result.track.id == track.id
    assert MIN_SCORE_THRESHOLD <= result.score < 1.0
    assert any("fallback tolerance" in reason for reason in result.reasons)


def test_duration_outside_fallback_no_match(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)
    ensure_library_schema(db_url)
    engine = create_library_engine(db_url)

    with Session(engine) as session:
        _seed_track(
            session,
            title="Far Track",
            artist="Window Artist",
            duration_ms=200000,
        )
        session.commit()

        result = TrackMatcher(session).match(
            TrackQuery(title="Far Track", artist="Window Artist", duration_ms=206500)
        )

    assert result.track is None
    assert result.score == 0.0


def test_alias_rescue_match(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)
    ensure_library_schema(db_url)
    engine = create_library_engine(db_url)

    with Session(engine) as session:
        track = _seed_track(
            session,
            title="Alpha Anthem",
            artist="Alias Artist",
            duration_ms=210000,
        )
        upsert_track_alias(
            session,
            TrackAlias(
                track_id=track.id,
                alias_type="alt_title",
                value="A Anthem",
                provider="test",
                source="fixture",
                confidence=0.9,
            ),
        )
        session.commit()

        result = TrackMatcher(session).match(
            TrackQuery(title="A Anthem", artist="Alias Artist", duration_ms=210000)
        )

    assert result.track is not None
    assert result.track.id == track.id
    assert result.alias_hit is True
    assert result.score >= MIN_SCORE_THRESHOLD
    assert any("alias rescue" in reason for reason in result.reasons)


def test_no_match_returns_none_track(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)
    ensure_library_schema(db_url)
    engine = create_library_engine(db_url)

    with Session(engine) as session:
        _seed_track(
            session,
            title="Known Track",
            artist="Known Artist",
            duration_ms=180000,
        )
        session.commit()

        result = TrackMatcher(session).match(
            TrackQuery(title="zzzxxyy", artist="qqqvvv", duration_ms=123456)
        )

    assert result.track is None
    assert result.score == 0.0


def test_canonical_matcher_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text("[library]\nname = \"COMMUNE\"\n", encoding="utf-8")
    monkeypatch.setenv("TAGSLUT_CONFIG", str(cfg_path))
    _clear_config_instance()

    class _ExplodingMatcher:
        def __init__(self, session: Session) -> None:
            raise AssertionError("TrackMatcher should not be constructed by default")

    monkeypatch.setattr(importer_module, "TrackMatcher", _ExplodingMatcher)

    db_url = f"sqlite:///{(tmp_path / 'importer.db').resolve()}"
    result = import_rekordbox_xml(FIXTURE_XML, db_url, dry_run=False)

    assert result.errors == []
    _clear_config_instance()
