from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

from sqlalchemy import select
from sqlalchemy.orm import Session

from tagslut.library import create_library_session_factory, ensure_library_schema
from tagslut.library.matcher import MIN_SCORE_THRESHOLD, TrackMatcher, TrackQuery
from tagslut.library.models import JobRun, Release, SourceProvenance, Track, TrackAlias, TrackFile
from tagslut.library.repositories import (
    get_track_by_alias,
    record_audit_event,
    upsert_track,
    upsert_track_alias,
    upsert_track_file,
)
from tagslut.utils.config import get_config

_REKORDBOX_PROVIDER = "rekordbox"
_REKORDBOX_SOURCE = "rekordbox_xml"


@dataclass(frozen=True)
class _ParsedTrack:
    source_key: str
    title: str
    artist_credit: str
    release_title: str | None
    mix_name: str | None
    path: str
    file_format: str | None
    bitrate: int | None
    sample_rate: int | None
    duration_ms: int | None


@dataclass
class ImportResult:
    tracks_seen: int = 0
    tracks_created: int = 0
    tracks_updated: int = 0
    errors: list[str] = field(default_factory=list)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sort_value(value: str) -> str:
    return " ".join(value.casefold().split())


def _parse_location(location: str) -> str:
    if not location:
        return ""
    parsed = urlparse(location)
    if parsed.scheme != "file":
        return unquote(location)
    if parsed.netloc and parsed.netloc != "localhost":
        return unquote(f"//{parsed.netloc}{parsed.path}")
    return unquote(parsed.path)


def _parse_duration_ms(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    try:
        raw = float(raw_value)
    except ValueError:
        return None
    if raw <= 0:
        return None
    if raw < 10_000:
        return int(raw * 1000)
    return int(raw)


def _parse_int(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    try:
        return int(float(raw_value))
    except ValueError:
        return None


def _parse_rekordbox_xml(xml_path: Path) -> list[_ParsedTrack]:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    collection = root.find("COLLECTION")
    if collection is None:
        raise ValueError(f"Rekordbox XML missing COLLECTION node: {xml_path}")

    parsed_tracks: list[_ParsedTrack] = []
    for track_node in collection.findall("TRACK"):
        source_key = (
            track_node.attrib.get("TrackID")
            or track_node.attrib.get("ID")
            or track_node.attrib.get("Key")
        )
        if not source_key:
            raise ValueError("Encountered Rekordbox TRACK without TrackID/ID/Key")

        title = (track_node.attrib.get("Name") or "").strip()
        artist_credit = (track_node.attrib.get("Artist") or "").strip()
        location = _parse_location(track_node.attrib.get("Location", ""))
        if not title:
            title = Path(location).stem or f"Track {source_key}"
        if not artist_credit:
            artist_credit = "Unknown Artist"

        parsed_tracks.append(
            _ParsedTrack(
                source_key=str(source_key),
                title=title,
                artist_credit=artist_credit,
                release_title=(track_node.attrib.get("Album") or None),
                mix_name=(track_node.attrib.get("Mix") or track_node.attrib.get("Remix") or None),
                path=location,
                file_format=(
                    track_node.attrib.get("Kind")
                    or (Path(location).suffix.lstrip(".").lower() if location else None)
                    or None
                ),
                bitrate=_parse_int(track_node.attrib.get("BitRate")),
                sample_rate=_parse_int(track_node.attrib.get("SampleRate")),
                duration_ms=_parse_duration_ms(track_node.attrib.get("TotalTime")),
            )
        )
    return parsed_tracks


def _get_or_create_release(session: Session, title: str | None, artist_credit: str) -> Release | None:
    if not title:
        return None
    existing = session.scalar(
        select(Release).where(
            Release.title == title,
            Release.artist_credit == artist_credit,
        )
    )
    if existing is not None:
        return existing
    release = Release(title=title, artist_credit=artist_credit)
    session.add(release)
    session.flush()
    return release


def _upsert_source_provenance(
    session: Session,
    *,
    track_id: str,
    source_key: str,
    payload_ref: str,
) -> SourceProvenance:
    existing = session.scalar(
        select(SourceProvenance).where(
            SourceProvenance.track_id == track_id,
            SourceProvenance.source_type == _REKORDBOX_SOURCE,
            SourceProvenance.source_key == source_key,
        )
    )
    if existing is not None:
        existing.payload_ref = payload_ref
        session.flush()
        return existing

    provenance = SourceProvenance(
        track_id=track_id,
        source_type=_REKORDBOX_SOURCE,
        source_key=source_key,
        payload_ref=payload_ref,
    )
    session.add(provenance)
    session.flush()
    return provenance


def _match_existing_track(session: Session, parsed_track: _ParsedTrack) -> Track | None:
    existing = get_track_by_alias(
        session,
        alias_type="rekordbox_track_id",
        value=parsed_track.source_key,
        provider=_REKORDBOX_PROVIDER,
    )
    if existing is not None:
        return existing
    if parsed_track.path:
        existing = get_track_by_alias(
            session,
            alias_type="file_path",
            value=parsed_track.path,
            provider=_REKORDBOX_PROVIDER,
        )
    if existing is not None:
        return existing
    if not _canonical_matcher_enabled():
        return None

    match_result = TrackMatcher(session).match(
        TrackQuery(
            title=parsed_track.title,
            artist=parsed_track.artist_credit,
            duration_ms=parsed_track.duration_ms,
            rekordbox_id=parsed_track.source_key,
            file_path=parsed_track.path or None,
        )
    )
    if match_result.track is not None and match_result.score >= MIN_SCORE_THRESHOLD:
        return match_result.track
    return None


def _canonical_matcher_enabled() -> bool:
    return bool(get_config().get("rekordbox.use_canonical_matcher", False))


def _track_payload(parsed_track: _ParsedTrack) -> dict[str, object]:
    return {
        "source_type": _REKORDBOX_SOURCE,
        "source_key": parsed_track.source_key,
        "title": parsed_track.title,
        "artist_credit": parsed_track.artist_credit,
        "release_title": parsed_track.release_title,
        "mix_name": parsed_track.mix_name,
        "path": parsed_track.path,
        "format": parsed_track.file_format,
        "bitrate": parsed_track.bitrate,
        "sample_rate": parsed_track.sample_rate,
        "duration_ms": parsed_track.duration_ms,
    }


def _preview_track(session: Session, job_run: JobRun, parsed_track: _ParsedTrack, result: ImportResult) -> None:
    existing = _match_existing_track(session, parsed_track)
    action = "preview_update" if existing is not None else "preview_create"
    entity_id = existing.id if existing is not None else parsed_track.source_key
    if existing is None:
        result.tracks_created += 1
    else:
        result.tracks_updated += 1
    record_audit_event(
        session,
        job_run.id,
        "track",
        entity_id,
        action,
        _track_payload(parsed_track),
    )


def _persist_track(session: Session, job_run: JobRun, parsed_track: _ParsedTrack, payload_ref: str) -> str:
    existing = _match_existing_track(session, parsed_track)
    release = _get_or_create_release(session, parsed_track.release_title, parsed_track.artist_credit)
    if existing is not None:
        existing.canonical_title = parsed_track.title
        existing.sort_title = _sort_value(parsed_track.title)
        existing.canonical_artist_credit = parsed_track.artist_credit
        existing.sort_artist_credit = _sort_value(parsed_track.artist_credit)
        existing.canonical_release_id = release.id if release is not None else None
        existing.canonical_mix_name = parsed_track.mix_name
        existing.status = "active"
        track = upsert_track(session, existing)
    else:
        track = upsert_track(
            session,
            Track(
                canonical_title=parsed_track.title,
                sort_title=_sort_value(parsed_track.title),
                canonical_artist_credit=parsed_track.artist_credit,
                sort_artist_credit=_sort_value(parsed_track.artist_credit),
                canonical_release_id=release.id if release is not None else None,
                canonical_mix_name=parsed_track.mix_name,
                status="active",
            ),
        )

    upsert_track_file(
        session,
        TrackFile(
            track_id=track.id,
            path=parsed_track.path,
            format=parsed_track.file_format,
            bitrate=parsed_track.bitrate,
            sample_rate=parsed_track.sample_rate,
            duration_ms=parsed_track.duration_ms,
            role="dj_derivative",
            is_preferred=True,
            active=True,
        ),
    )
    upsert_track_alias(
        session,
        TrackAlias(
            track_id=track.id,
            alias_type="rekordbox_track_id",
            value=parsed_track.source_key,
            provider=_REKORDBOX_PROVIDER,
            source=_REKORDBOX_SOURCE,
            confidence=1.0,
        ),
    )
    if parsed_track.path:
        upsert_track_alias(
            session,
            TrackAlias(
                track_id=track.id,
                alias_type="file_path",
                value=parsed_track.path,
                provider=_REKORDBOX_PROVIDER,
                source=_REKORDBOX_SOURCE,
                confidence=1.0,
            ),
        )
    _upsert_source_provenance(
        session,
        track_id=track.id,
        source_key=parsed_track.source_key,
        payload_ref=payload_ref,
    )
    record_audit_event(
        session,
        job_run.id,
        "track",
        track.id,
        "updated" if existing is not None else "created",
        _track_payload(parsed_track),
    )
    return "updated" if existing is not None else "created"


def _persist_failure_audit(db_url: str, xml_path: Path, errors: list[str]) -> None:
    session_factory = create_library_session_factory(db_url)
    with session_factory() as session:
        job_run = JobRun(
            job_type="import_rekordbox_xml",
            dry_run=False,
            status="failed",
            started_at=_utcnow(),
            finished_at=_utcnow(),
        )
        session.add(job_run)
        session.flush()
        record_audit_event(
            session,
            job_run.id,
            "import",
            str(xml_path),
            "failed",
            {"errors": errors},
        )
        session.commit()


def import_rekordbox_xml(xml_path: Path, db_url: str, *, dry_run: bool = True) -> ImportResult:
    xml_path = xml_path.expanduser().resolve()
    resolved_db_url = ensure_library_schema(db_url)
    session_factory = create_library_session_factory(resolved_db_url)
    parsed_tracks = _parse_rekordbox_xml(xml_path)
    result = ImportResult()
    payload_ref = str(xml_path)

    if dry_run:
        with session_factory() as session:
            job_run = JobRun(
                job_type="import_rekordbox_xml",
                dry_run=True,
                status="running",
                started_at=_utcnow(),
            )
            session.add(job_run)
            session.flush()

            for parsed_track in parsed_tracks:
                result.tracks_seen += 1
                try:
                    _preview_track(session, job_run, parsed_track, result)
                except Exception as exc:
                    message = f"{parsed_track.source_key}: {exc}"
                    result.errors.append(message)
                    record_audit_event(
                        session,
                        job_run.id,
                        "track",
                        parsed_track.source_key,
                        "preview_error",
                        {"error": message},
                    )

            job_run.status = "dry_run"
            job_run.finished_at = _utcnow()
            session.commit()

        print(
            "Preview summary: "
            f"seen={result.tracks_seen} "
            f"create={result.tracks_created} "
            f"update={result.tracks_updated} "
            f"errors={len(result.errors)}"
        )
        return result

    try:
        with session_factory() as session:
            job_run = JobRun(
                job_type="import_rekordbox_xml",
                dry_run=False,
                status="running",
                started_at=_utcnow(),
            )
            session.add(job_run)
            session.flush()

            for parsed_track in parsed_tracks:
                result.tracks_seen += 1
                try:
                    action = _persist_track(session, job_run, parsed_track, payload_ref)
                except Exception as exc:
                    result.errors.append(f"{parsed_track.source_key}: {exc}")
                    continue
                if action == "created":
                    result.tracks_created += 1
                else:
                    result.tracks_updated += 1

            if result.errors:
                raise RuntimeError("; ".join(result.errors))

            job_run.status = "completed"
            job_run.finished_at = _utcnow()
            session.commit()
    except RuntimeError:
        _persist_failure_audit(resolved_db_url, xml_path, result.errors)
        return result

    return result
