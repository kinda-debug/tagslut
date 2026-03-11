from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEvent, Track, TrackAlias, TrackFile


def _copy_fields(target: object, source: object, field_names: tuple[str, ...]) -> None:
    for field_name in field_names:
        setattr(target, field_name, getattr(source, field_name))


def upsert_track(session: Session, track: Track) -> Track:
    existing = session.get(Track, track.id) if track.id else None
    if existing is None:
        existing = session.scalar(
            select(Track).where(
                Track.canonical_title == track.canonical_title,
                Track.sort_title == track.sort_title,
                Track.canonical_artist_credit == track.canonical_artist_credit,
                Track.sort_artist_credit == track.sort_artist_credit,
                Track.canonical_release_id == track.canonical_release_id,
                Track.canonical_mix_name == track.canonical_mix_name,
            )
        )
    if existing is None:
        session.add(track)
        session.flush()
        return track

    _copy_fields(
        existing,
        track,
        (
            "canonical_title",
            "sort_title",
            "canonical_artist_credit",
            "sort_artist_credit",
            "canonical_release_id",
            "canonical_mix_name",
            "status",
        ),
    )
    session.flush()
    return existing


def upsert_track_file(session: Session, track_file: TrackFile) -> TrackFile:
    existing = session.get(TrackFile, track_file.id) if track_file.id else None
    if existing is None:
        existing = session.scalar(select(TrackFile).where(TrackFile.path == track_file.path))
    if existing is None:
        session.add(track_file)
        session.flush()
        return track_file

    _copy_fields(
        existing,
        track_file,
        (
            "track_id",
            "file_hash_sha256",
            "acoustic_fingerprint",
            "format",
            "bitrate",
            "sample_rate",
            "duration_ms",
            "role",
            "derived_from_file_id",
            "is_preferred",
            "active",
        ),
    )
    session.flush()
    return existing


def upsert_track_alias(session: Session, alias: TrackAlias) -> TrackAlias:
    provider = alias.provider or ""
    existing = session.get(TrackAlias, alias.id) if alias.id else None
    if existing is None:
        existing = session.scalar(
            select(TrackAlias).where(
                TrackAlias.alias_type == alias.alias_type,
                TrackAlias.value == alias.value,
                TrackAlias.provider == provider,
            )
        )
    if existing is None:
        alias.provider = provider
        session.add(alias)
        session.flush()
        return alias

    existing.track_id = alias.track_id
    existing.source = alias.source
    existing.confidence = alias.confidence
    session.flush()
    return existing


def get_track_by_alias(
    session: Session,
    alias_type: str,
    value: str,
    provider: str | None = None,
) -> Track | None:
    query = (
        select(Track)
        .join(TrackAlias, TrackAlias.track_id == Track.id)
        .where(
            TrackAlias.alias_type == alias_type,
            TrackAlias.value == value,
        )
    )
    if provider is not None:
        query = query.where(TrackAlias.provider == (provider or ""))
    return session.scalar(query.limit(1))


def record_audit_event(
    session: Session,
    job_run_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    payload: dict[str, Any],
) -> None:
    session.add(
        AuditEvent(
            job_run_id=job_run_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            payload_json=payload,
        )
    )
    session.flush()
