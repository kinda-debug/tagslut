from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tagslut.adapters.rekordbox.importer import import_rekordbox_xml
from tagslut.library import create_library_engine
from tagslut.library.models import AuditEvent, JobRun, SourceProvenance, Track, TrackAlias, TrackFile

FIXTURE_XML = Path(__file__).resolve().parent / "fixtures" / "small_rekordbox.xml"


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'library.db').resolve()}"


def _count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_import_rekordbox_dry_run(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)

    result = import_rekordbox_xml(FIXTURE_XML, db_url, dry_run=True)

    assert result.tracks_seen == 2
    assert result.tracks_created == 2
    assert result.tracks_updated == 0
    assert result.errors == []

    engine = create_library_engine(db_url)
    with Session(engine) as session:
        assert _count(session, Track) == 0
        assert _count(session, TrackAlias) == 0
        assert _count(session, TrackFile) == 0
        assert _count(session, SourceProvenance) == 0
        assert _count(session, JobRun) == 1
        assert _count(session, AuditEvent) == 2

        job_run = session.scalar(select(JobRun))
        assert job_run is not None
        assert job_run.dry_run is True
        assert job_run.status == "dry_run"

        actions = list(session.scalars(select(AuditEvent.action)))
        assert actions == ["preview_create", "preview_create"]


def test_import_rekordbox_live(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)

    result = import_rekordbox_xml(FIXTURE_XML, db_url, dry_run=False)

    assert result.tracks_seen == 2
    assert result.tracks_created == 2
    assert result.tracks_updated == 0
    assert result.errors == []

    engine = create_library_engine(db_url)
    with Session(engine) as session:
        tracks = list(session.scalars(select(Track).order_by(Track.canonical_title)))
        assert [track.canonical_title for track in tracks] == ["First Track", "Second Track"]
        assert [track.canonical_artist_credit for track in tracks] == ["Alpha Artist", "Beta Artist"]
        assert tracks[0].canonical_mix_name == "Extended Mix"
        assert tracks[1].canonical_mix_name is None

        aliases = list(session.scalars(select(TrackAlias).order_by(TrackAlias.alias_type, TrackAlias.value)))
        assert len(aliases) == 4
        assert {(alias.alias_type, alias.value) for alias in aliases} == {
            ("file_path", "/Users/test/Music/Alpha Artist/First Track.mp3"),
            ("file_path", "/Users/test/Music/Beta Artist/Second Track.mp3"),
            ("rekordbox_track_id", "1"),
            ("rekordbox_track_id", "2"),
        }
        assert {alias.provider for alias in aliases} == {"rekordbox"}
        assert {alias.source for alias in aliases} == {"rekordbox_xml"}

        files = list(session.scalars(select(TrackFile).order_by(TrackFile.path)))
        assert len(files) == 2
        assert {track_file.role for track_file in files} == {"dj_derivative"}
        assert all(track_file.is_preferred for track_file in files)
        assert {track_file.duration_ms for track_file in files} == {198000, 245000}


def test_upsert_idempotent(tmp_path: Path) -> None:
    db_url = _db_url(tmp_path)

    first = import_rekordbox_xml(FIXTURE_XML, db_url, dry_run=False)
    second = import_rekordbox_xml(FIXTURE_XML, db_url, dry_run=False)

    assert first.errors == []
    assert second.errors == []
    assert second.tracks_seen == 2
    assert second.tracks_created == 0
    assert second.tracks_updated == 2

    engine = create_library_engine(db_url)
    with Session(engine) as session:
        assert _count(session, Track) == 2
        assert _count(session, TrackAlias) == 4
        assert _count(session, TrackFile) == 2
        assert _count(session, SourceProvenance) == 2
        assert _count(session, JobRun) == 2
        assert _count(session, AuditEvent) == 4
