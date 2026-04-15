from __future__ import annotations

import getpass
import json
import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

import click
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, selectinload

from tagslut.cli.commands._cohort_state import (
    EARLY_BLOCKED_STAGES,
    blocked_rows_for_cohort,
    build_output_artifacts,
    cohort_paths,
    cohort_requires_fix_message,
    create_cohort,
    ensure_cohort_support,
    find_cohort_by_source,
    find_latest_blocked_cohort_for_source,
    mark_cohort_file_blocked,
    mark_paths_ok,
    record_blocked_paths,
    refresh_cohort_status,
    resolve_flac_paths,
    retag_flac_paths,
    set_cohort_blocked,
    set_cohort_running,
)
from tagslut.dj.key_utils import classical_to_camelot, normalize_key
from tagslut.library import (
    DEFAULT_LIBRARY_DB_URL,
    create_library_session_factory,
    ensure_library_schema,
    resolve_library_db_url,
)
from tagslut.library.matcher import MatchResult, TrackMatcher, TrackQuery
from tagslut.library.models import (
    ApprovedMetadata,
    AuditEvent,
    ExportWriteLog,
    JobRun,
    MatchCandidate,
    MetadataCandidate,
    RawProviderResult,
    SourceProvenance,
    Track,
    TrackAlias,
    TrackFile,
)
from tagslut.library.repositories import get_track_by_alias, record_audit_event, upsert_track_alias
from tagslut.storage.queries import get_files_for_library_track
from tagslut.storage.schema import init_db
from tagslut.tag.providers import get_provider
from tagslut.tag.providers.base import FieldCandidate, ProviderConfigError, RawResult
from tagslut.tag.rekordbox_compat import REKORDBOX_TESTED_FIELDS, REKORDBOX_XML_FIELD_MAP
from tagslut.utils.config import get_config
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path
from tagslut.utils.env_paths import get_library_volume

logger = logging.getLogger("tagslut.tag")

_CANONICAL_DISAGREEMENT_FIELDS = frozenset(
    {"canonical_title", "canonical_artist_credit", "bpm", "musical_key"}
)
_FILE_TAG_FIELD_MAP = {
    "canonical_title": "title",
    "canonical_artist_credit": "artist",
    "bpm": "bpm",
    "musical_key": "initialkey",
    "comments": "comment",
}
_BATCH_SOURCE_TYPES = ("tag_batch", "batch")
_SYNC_FIELD_COLUMN_MAP = {
    "canonical_title": ("canonical_title",),
    "canonical_artist_credit": ("canonical_artist",),
    "canonical_bpm": ("canonical_bpm", "bpm"),
    "canonical_genre": ("canonical_genre", "genre"),
    "canonical_energy": ("canonical_energy",),
    "canonical_danceability": ("canonical_danceability",),
    "canonical_valence": ("canonical_valence",),
    "canonical_label": ("canonical_label",),
    "canonical_mix_name": ("canonical_mix_name",),
    "canonical_year": ("canonical_year",),
    "canonical_release_date": ("canonical_release_date",),
    "canonical_explicit": ("canonical_explicit",),
}


@dataclass(frozen=True)
class _AutoApprovalDecision:
    winner_id: str | None
    status_by_candidate_id: dict[str, str]
    rationale_by_candidate_id: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class _BatchWorkItem:
    provenance: SourceProvenance
    track: Track | None


@dataclass
class _SyncToFilesSummary:
    files_updated: set[str] = field(default_factory=set)
    fields_written: int = 0
    skipped_null_source: int = 0
    skipped_already_set: int = 0
    warnings: int = 0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_db_url() -> str:
    return str(get_config().get("library.db_url", DEFAULT_LIBRARY_DB_URL))


def _session_factory(db_url: str | None = None):
    resolved_db_url = ensure_library_schema(db_url or _default_db_url())
    return create_library_session_factory(resolved_db_url)


def _create_job_run(session: Session, *, job_type: str, dry_run: bool) -> JobRun:
    job_run = JobRun(
        job_type=job_type,
        dry_run=dry_run,
        status="running",
        started_at=_utcnow(),
    )
    session.add(job_run)
    session.flush()
    return job_run


def _batch_items_for_batch(session: Session, batch_id: str) -> list[_BatchWorkItem]:
    rows = list(
        session.scalars(
            select(SourceProvenance)
            .where(
                SourceProvenance.source_type.in_(_BATCH_SOURCE_TYPES),
                SourceProvenance.source_key == batch_id,
            )
            .options(
                selectinload(SourceProvenance.track).selectinload(Track.aliases),
                selectinload(SourceProvenance.track).selectinload(Track.files),
            )
            .order_by(SourceProvenance.first_seen_at.asc(), SourceProvenance.id.asc())
        )
    )
    items: list[_BatchWorkItem] = []
    for provenance in rows:
        track = provenance.track
        if track is not None and track.status != "active":
            continue
        items.append(_BatchWorkItem(provenance=provenance, track=track))
    return items


def _build_track_query(item: _BatchWorkItem) -> TrackQuery:
    if item.track is None:
        return TrackQuery(
            title="",
            artist="",
        )

    track = item.track
    aliases_by_type = {alias.alias_type: alias.value for alias in track.aliases}
    preferred_file = next(
        (
            track_file
            for track_file in track.files
            if track_file.active and track_file.is_preferred
        ),
        None,
    )
    fallback_file = next((track_file for track_file in track.files if track_file.active), None)
    track_file = preferred_file or fallback_file
    return TrackQuery(
        title=track.canonical_title,
        artist=track.canonical_artist_credit,
        duration_ms=track_file.duration_ms if track_file is not None else None,
        rekordbox_id=aliases_by_type.get("rekordbox_track_id"),
        file_path=track_file.path if track_file is not None else None,
        isrc=aliases_by_type.get("isrc"),
        fingerprint=(
            track_file.acoustic_fingerprint
            if track_file is not None and track_file.acoustic_fingerprint
            else (track_file.file_hash_sha256 if track_file is not None else None)
        ),
    )


def _first_field_value(field_candidates: list[FieldCandidate], field_name: str) -> Any | None:
    for field_candidate in field_candidates:
        if field_candidate.field_name == field_name:
            return field_candidate.normalized_value
    return None


def _match_query_for_raw(
    source_query: TrackQuery,
    raw_result: RawResult,
    field_candidates: list[FieldCandidate],
) -> TrackQuery:
    title = _first_field_value(field_candidates, "canonical_title")
    artist = _first_field_value(field_candidates, "canonical_artist_credit")
    isrc = _first_field_value(field_candidates, "isrc")
    file_path = _first_field_value(field_candidates, "file_path")
    fingerprint = (
        _first_field_value(field_candidates, "fingerprint")
        or _first_field_value(field_candidates, "acoustic_fingerprint")
        or _first_field_value(field_candidates, "file_hash_sha256")
        or raw_result.payload.get("fingerprint")
        or raw_result.payload.get("file_hash_sha256")
    )
    return TrackQuery(
        title=str(title) if isinstance(title, str) else source_query.title,
        artist=str(artist) if isinstance(artist, str) else source_query.artist,
        duration_ms=source_query.duration_ms,
        rekordbox_id=source_query.rekordbox_id,
        file_path=str(file_path) if isinstance(file_path, str) else source_query.file_path,
        isrc=str(isrc) if isinstance(isrc, str) else source_query.isrc,
        fingerprint=str(fingerprint) if isinstance(fingerprint, str) else source_query.fingerprint,
    )


def _insert_raw_result(session: Session, *, batch_id: str, raw: RawResult) -> RawProviderResult:
    raw_row = RawProviderResult(
        batch_id=batch_id,
        provider=raw.provider,
        external_id=raw.external_id,
        query_text=raw.query_text,
        payload_json=raw.payload,
        fetched_at=_utcnow(),
    )
    session.add(raw_row)
    session.flush()
    return raw_row


def _insert_match_candidate(
    session: Session,
    *,
    raw_result_id: str,
    match_result: MatchResult,
) -> MatchCandidate:
    match_candidate = MatchCandidate(
        raw_result_id=raw_result_id,
        track_id=match_result.track.id if match_result.track is not None else None,
        score=match_result.score,
        reasons_json=list(match_result.reasons),
        status="matched" if match_result.track is not None else "unmatched",
    )
    session.add(match_candidate)
    session.flush()
    return match_candidate


def _insert_metadata_candidate(
    session: Session,
    *,
    track_id: str | None,
    raw_result_id: str,
    field_candidate: FieldCandidate,
    status: str = "pending",
    is_user_override: bool = False,
) -> MetadataCandidate:
    metadata_candidate = MetadataCandidate(
        track_id=track_id,
        raw_result_id=raw_result_id,
        field_name=field_candidate.field_name,
        normalized_value_json=field_candidate.normalized_value,
        confidence=float(field_candidate.confidence),
        rationale_json=dict(field_candidate.rationale),
        status=status,
        is_user_override=is_user_override,
    )
    session.add(metadata_candidate)
    session.flush()
    return metadata_candidate


def _candidate_rows_for_batch(
    session: Session,
    batch_id: str,
    *,
    status: str | None = None,
) -> list[tuple[MetadataCandidate, RawProviderResult]]:
    statement = (
        select(MetadataCandidate, RawProviderResult)
        .join(RawProviderResult, RawProviderResult.id == MetadataCandidate.raw_result_id)
        .where(RawProviderResult.batch_id == batch_id)
        .order_by(
            MetadataCandidate.track_id.asc(),
            MetadataCandidate.field_name.asc(),
            MetadataCandidate.confidence.desc(),
            MetadataCandidate.id.asc(),
        )
    )
    if status is not None:
        statement = statement.where(MetadataCandidate.status == status)
    return list(session.execute(statement).all())


def _value_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _candidate_group_track_key(candidate: MetadataCandidate) -> str:
    if candidate.track_id is not None:
        return candidate.track_id
    return f"raw:{candidate.raw_result_id}"


def _resolve_auto_approval(
    candidates: list[tuple[MetadataCandidate, RawProviderResult]],
) -> _AutoApprovalDecision:
    if not candidates:
        return _AutoApprovalDecision(None, {}, {})

    status_map = {candidate.id: "pending" for candidate, _ in candidates}
    rationale_map: dict[str, dict[str, Any]] = {}

    overrides = [candidate for candidate, _ in candidates if candidate.is_user_override]
    if overrides:
        winner = max(overrides, key=lambda candidate: (candidate.confidence, candidate.id))
        status_map[winner.id] = "approved"
        rationale_map[winner.id] = {"decision": "user_override"}
        return _AutoApprovalDecision(winner.id, status_map, rationale_map)

    sorted_candidates = sorted(
        (candidate for candidate, _ in candidates),
        key=lambda candidate: (candidate.confidence, candidate.id),
        reverse=True,
    )
    top_candidate = sorted_candidates[0]
    top_value_key = _value_key(top_candidate.normalized_value_json)
    competing = [
        candidate
        for candidate in sorted_candidates[1:]
        if _value_key(candidate.normalized_value_json) != top_value_key
    ]
    top_margin = top_candidate.confidence - competing[0].confidence if competing else top_candidate.confidence
    disagreement = (
        top_candidate.field_name in _CANONICAL_DISAGREEMENT_FIELDS
        and len({_value_key(candidate.normalized_value_json) for candidate, _ in candidates}) > 1
    )
    has_strong_competitor = any(candidate.confidence > 0.70 for candidate in competing)
    auto_approve = (
        top_candidate.confidence > 0.90
        and top_margin > 0.15
        and not has_strong_competitor
        and not disagreement
    )

    rationale_map[top_candidate.id] = {
        "decision": "auto_approved" if auto_approve else "review_required",
        "top_margin": top_margin,
        "disagreement": disagreement,
        "has_strong_competitor": has_strong_competitor,
    }
    if auto_approve:
        status_map[top_candidate.id] = "approved"
        return _AutoApprovalDecision(top_candidate.id, status_map, rationale_map)
    return _AutoApprovalDecision(None, status_map, rationale_map)


def _apply_auto_approval_rules(session: Session, batch_id: str) -> None:
    grouped: dict[tuple[str, str], list[tuple[MetadataCandidate, RawProviderResult]]] = defaultdict(list)
    for candidate, raw_result in _candidate_rows_for_batch(session, batch_id):
        grouped[(_candidate_group_track_key(candidate), candidate.field_name)].append((candidate, raw_result))

    for candidates in grouped.values():
        decision = _resolve_auto_approval(candidates)
        for candidate, _ in candidates:
            candidate.status = decision.status_by_candidate_id.get(candidate.id, candidate.status)
            if candidate.id in decision.rationale_by_candidate_id:
                rationale = dict(candidate.rationale_json)
                rationale["auto_review"] = decision.rationale_by_candidate_id[candidate.id]
                candidate.rationale_json = rationale
    session.flush()


def _job_summary_payload(
    *,
    batch_id: str,
    provider_name: str,
    tracks_seen: int,
    raw_results: int,
    metadata_candidates: int,
    match_candidates: int,
) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "provider": provider_name,
        "tracks_seen": tracks_seen,
        "raw_results": raw_results,
        "metadata_candidates": metadata_candidates,
        "match_candidates": match_candidates,
    }


def run_tag_fetch(
    provider_name: str,
    batch_id: str,
    *,
    dry_run: bool = False,
    db_url: str | None = None,
) -> JobRun:
    try:
        provider = get_provider(provider_name)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc

    session_factory = _session_factory(db_url)
    with session_factory() as session:
        items = _batch_items_for_batch(session, batch_id)
        matcher = TrackMatcher(session)
        job_run = _create_job_run(session, job_type="tag_fetch", dry_run=dry_run)

        raw_result_count = 0
        metadata_candidate_count = 0
        match_candidate_count = 0

        for item in items:
            track_query = _build_track_query(item)
            try:
                raw_results = provider.search(track_query)
            except ProviderConfigError as exc:
                raise click.ClickException(str(exc)) from exc
            track_raw_count = 0
            track_metadata_count = 0
            track_match_count = 0

            for raw_result in raw_results:
                field_candidates = provider.normalize(raw_result)
                match_result = matcher.match(
                    _match_query_for_raw(track_query, raw_result, field_candidates)
                )
                resolved_track = item.track or match_result.track
                if (
                    not dry_run
                    and item.track is None
                    and match_result.track is not None
                    and item.provenance.track_id is None
                ):
                    item.provenance.track_id = match_result.track.id
                track_raw_count += 1
                track_metadata_count += len(field_candidates)
                if match_result.track is not None:
                    track_match_count += 1

                if dry_run:
                    continue

                raw_row = _insert_raw_result(session, batch_id=batch_id, raw=raw_result)
                _insert_match_candidate(
                    session,
                    raw_result_id=raw_row.id,
                    match_result=match_result,
                )
                for field_candidate in field_candidates:
                    _insert_metadata_candidate(
                        session,
                        track_id=resolved_track.id if resolved_track is not None else None,
                        raw_result_id=raw_row.id,
                        field_candidate=field_candidate,
                    )

            raw_result_count += track_raw_count
            metadata_candidate_count += track_metadata_count
            match_candidate_count += track_match_count
            record_audit_event(
                session,
                job_run.id,
                "track" if item.track is not None else "source_provenance",
                item.track.id if item.track is not None else item.provenance.id,
                "tag_fetch_preview" if dry_run else "tag_fetch",
                {
                    "batch_id": batch_id,
                    "provider": provider.name,
                    "raw_results": track_raw_count,
                    "metadata_candidates": track_metadata_count,
                    "match_hits": track_match_count,
                },
            )

        if not dry_run:
            _apply_auto_approval_rules(session, batch_id)

        job_run.status = "dry_run" if dry_run else "completed"
        job_run.finished_at = _utcnow()
        record_audit_event(
            session,
            job_run.id,
            "batch",
            batch_id,
            "tag_fetch_complete",
            _job_summary_payload(
                batch_id=batch_id,
                provider_name=provider.name,
                tracks_seen=len(items),
                raw_results=raw_result_count,
                metadata_candidates=metadata_candidate_count,
                match_candidates=match_candidate_count,
            ),
        )
        session.commit()
        return job_run


def _upsert_batch_source_provenance(
    session: Session,
    *,
    batch_id: str,
    track_id: str | None,
    payload_ref: str,
) -> None:
    existing = session.scalar(
        select(SourceProvenance).where(
            SourceProvenance.source_type == "tag_batch",
            SourceProvenance.source_key == batch_id,
            SourceProvenance.payload_ref == payload_ref,
        )
    )
    if existing is not None:
        if existing.track_id is None and track_id is not None:
            existing.track_id = track_id
        return

    session.add(
        SourceProvenance(
            track_id=track_id,
            source_type="tag_batch",
            source_key=batch_id,
            payload_ref=payload_ref,
        )
    )
    session.flush()


def run_tag_batch_create(
    source: str,
    playlist_id: str,
    batch_id: str,
    *,
    db_url: str | None = None,
) -> int:
    raise click.ClickException(f"Unsupported batch source: {source}")


def _review_grouped_candidates(
    session: Session,
    batch_id: str,
) -> dict[tuple[str, str], list[tuple[MetadataCandidate, RawProviderResult]]]:
    grouped: dict[tuple[str, str], list[tuple[MetadataCandidate, RawProviderResult]]] = defaultdict(list)
    for candidate, raw_result in _candidate_rows_for_batch(session, batch_id):
        if candidate.track_id is None:
            continue
        grouped[(candidate.track_id, candidate.field_name)].append((candidate, raw_result))
    return grouped


def _parse_override_value(raw_value: str) -> Any:
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


def run_tag_review(batch_id: str, *, db_url: str | None = None) -> int:
    session_factory = _session_factory(db_url)
    reviewed_groups = 0

    with session_factory() as session:
        grouped = _review_grouped_candidates(session, batch_id)
        for (track_id, field_name), candidates in grouped.items():
            track = session.get(Track, track_id)
            if track is None:
                continue

            current = session.scalar(
                select(ApprovedMetadata).where(
                    ApprovedMetadata.track_id == track_id,
                    ApprovedMetadata.field_name == field_name,
                )
            )

            click.echo(f"\nTrack: {track.canonical_artist_credit} - {track.canonical_title}")
            click.echo(f"Field: {field_name}")
            click.echo(
                "Current approved: "
                + ("NONE" if current is None else json.dumps(current.value_json, ensure_ascii=False))
            )
            for candidate, raw_result in candidates:
                click.echo(
                    f"  {candidate.id} score={candidate.confidence:.2f} "
                    f"status={candidate.status} provider={raw_result.provider} "
                    f"value={json.dumps(candidate.normalized_value_json, ensure_ascii=False)} "
                    f"rationale={json.dumps(candidate.rationale_json, ensure_ascii=False)}"
                )

            response = click.prompt("Action", default="skip", show_default=True).strip()
            if response == "skip":
                continue
            if response == "reject":
                for candidate, _ in candidates:
                    candidate.status = "rejected"
                reviewed_groups += 1
                continue
            if response.startswith("approve "):
                candidate_id = response.split(" ", 1)[1].strip()
                matched = False
                for candidate, _ in candidates:
                    if candidate.id == candidate_id:
                        candidate.status = "approved"
                        rationale = dict(candidate.rationale_json)
                        rationale["approved_by"] = getpass.getuser()
                        candidate.rationale_json = rationale
                        matched = True
                    elif candidate.status == "approved":
                        candidate.status = "pending"
                if not matched:
                    raise click.ClickException(f"Unknown candidate id: {candidate_id}")
                reviewed_groups += 1
                continue
            if response.startswith("override "):
                override_value = _parse_override_value(response.split(" ", 1)[1].strip())
                source_candidate, _ = candidates[0]
                session.add(
                    MetadataCandidate(
                        track_id=track_id,
                        raw_result_id=source_candidate.raw_result_id,
                        field_name=field_name,
                        normalized_value_json=override_value,
                        confidence=1.0,
                        rationale_json={
                            "approved_by": getpass.getuser(),
                            "action": "override",
                        },
                        status="approved",
                        is_user_override=True,
                    )
                )
                reviewed_groups += 1
                continue
            raise click.ClickException(f"Unknown review action: {response}")

        session.commit()
    return reviewed_groups


def _approved_candidate_groups(
    session: Session,
    batch_id: str,
) -> dict[tuple[str, str], list[MetadataCandidate]]:
    grouped: dict[tuple[str, str], list[MetadataCandidate]] = defaultdict(list)
    for candidate, _ in _candidate_rows_for_batch(session, batch_id, status="approved"):
        if candidate.track_id is None:
            continue
        grouped[(candidate.track_id, candidate.field_name)].append(candidate)
    return grouped


def _choose_candidate_for_apply(candidates: list[MetadataCandidate]) -> MetadataCandidate:
    overrides = [candidate for candidate in candidates if candidate.is_user_override]
    if overrides:
        return max(overrides, key=lambda candidate: (candidate.confidence, candidate.id))
    return max(candidates, key=lambda candidate: (candidate.confidence, candidate.id))


def _apply_metadata_candidate(session: Session, winner: MetadataCandidate) -> tuple[bool, str]:
    if winner.track_id is None:
        return False, "skipped_unlinked"

    existing = session.scalar(
        select(ApprovedMetadata).where(
            ApprovedMetadata.track_id == winner.track_id,
            ApprovedMetadata.field_name == winner.field_name,
        )
    )
    if existing is None:
        session.add(
            ApprovedMetadata(
                track_id=winner.track_id,
                field_name=winner.field_name,
                value_json=winner.normalized_value_json,
                approved_from_candidate_id=winner.id,
                approved_by=str(winner.rationale_json.get("approved_by") or "auto"),
                approved_at=_utcnow(),
                is_user_override=bool(winner.is_user_override),
            )
        )
        return True, "inserted"

    if winner.is_user_override:
        existing.value_json = winner.normalized_value_json
        existing.approved_from_candidate_id = winner.id
        existing.approved_by = str(winner.rationale_json.get("approved_by") or "override")
        existing.approved_at = _utcnow()
        existing.is_user_override = True
        return True, "overridden"

    return False, "skipped_existing"


def run_tag_apply(batch_id: str, *, db_url: str | None = None) -> JobRun:
    session_factory = _session_factory(db_url)

    with session_factory() as session:
        _apply_auto_approval_rules(session, batch_id)
        job_run = _create_job_run(session, job_type="tag_apply", dry_run=False)

        for (track_id, field_name), candidates in _approved_candidate_groups(session, batch_id).items():
            winner = _choose_candidate_for_apply(candidates)
            applied, action = _apply_metadata_candidate(session, winner)

            record_audit_event(
                session,
                job_run.id,
                "metadata_candidate",
                winner.id,
                "tag_apply",
                {
                    "batch_id": batch_id,
                    "track_id": track_id,
                    "field_name": field_name,
                    "action": action,
                    "applied": applied,
                    "is_user_override": bool(winner.is_user_override),
                },
            )

        job_run.status = "completed"
        job_run.finished_at = _utcnow()
        session.commit()
        return job_run


def _resolve_fetch_job(session: Session, job_id_or_last: str) -> JobRun:
    if job_id_or_last == "last":
        job_run = session.scalar(
            select(JobRun)
            .where(JobRun.job_type == "tag_fetch", JobRun.dry_run.is_(False))
            .order_by(JobRun.started_at.desc())
        )
        if job_run is None:
            raise click.ClickException("No prior live tag fetch job found")
        return job_run

    job_run = session.get(JobRun, job_id_or_last)
    if job_run is None or job_run.job_type != "tag_fetch":
        raise click.ClickException(f"Unknown tag fetch job: {job_id_or_last}")
    return job_run


def _resolve_batch_id_for_fetch_job(session: Session, fetch_job: JobRun) -> str:
    for audit_event in session.scalars(
        select(AuditEvent)
        .where(AuditEvent.job_run_id == fetch_job.id)
        .order_by(AuditEvent.created_at.asc())
    ):
        payload = audit_event.payload_json or {}
        if isinstance(payload, dict) and payload.get("batch_id"):
            return str(payload["batch_id"])

    if session.scalar(select(RawProviderResult.id).where(RawProviderResult.batch_id == fetch_job.id).limit(1)):
        return fetch_job.id
    raise click.ClickException(f"Could not resolve batch for fetch job: {fetch_job.id}")


def _approved_metadata_rows_for_batch(
    session: Session,
    batch_id: str,
) -> list[tuple[ApprovedMetadata, MetadataCandidate, RawProviderResult]]:
    return list(
        session.execute(
            select(ApprovedMetadata, MetadataCandidate, RawProviderResult)
            .join(
                MetadataCandidate,
                MetadataCandidate.id == ApprovedMetadata.approved_from_candidate_id,
            )
            .join(
                RawProviderResult,
                RawProviderResult.id == MetadataCandidate.raw_result_id,
            )
            .where(RawProviderResult.batch_id == batch_id)
            .order_by(ApprovedMetadata.track_id.asc(), ApprovedMetadata.field_name.asc())
        ).all()
    )


def _track_rekordbox_xml_path(session: Session, track_id: str) -> Path | None:
    payload_ref = session.scalar(
        select(SourceProvenance.payload_ref).where(
            SourceProvenance.track_id == track_id,
            SourceProvenance.source_type == "rekordbox_xml",
        )
    )
    if not payload_ref:
        return None
    return Path(str(payload_ref)).expanduser().resolve()


def _track_rekordbox_identity(session: Session, track_id: str) -> tuple[str | None, str | None]:
    aliases = list(
        session.scalars(
            select(TrackAlias).where(
                TrackAlias.track_id == track_id,
                TrackAlias.alias_type.in_(("rekordbox_track_id", "file_path")),
            )
        )
    )
    rekordbox_id = next(
        (alias.value for alias in aliases if alias.alias_type == "rekordbox_track_id"),
        None,
    )
    file_path = next(
        (alias.value for alias in aliases if alias.alias_type == "file_path"),
        None,
    )
    return rekordbox_id, file_path


def _parse_rekordbox_location(location: str) -> str:
    if not location:
        return ""
    parsed = urlparse(location)
    if parsed.scheme != "file":
        return unquote(location)
    if parsed.netloc and parsed.netloc != "localhost":
        return unquote(f"//{parsed.netloc}{parsed.path}")
    return unquote(parsed.path)


def _stringify_export_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _write_export_log(
    session: Session,
    *,
    job_run_id: str,
    track_id: str,
    target: str,
    field_name: str,
    old_value: Any,
    new_value: Any,
    status: str,
) -> None:
    session.add(
        ExportWriteLog(
            job_run_id=job_run_id,
            track_id=track_id,
            target=target,
            field_name=field_name,
            old_value_json=old_value,
            new_value_json=new_value,
            status=status,
            written_at=_utcnow(),
        )
    )
    session.flush()


def _find_rekordbox_track_node(
    tree: ET.ElementTree,
    *,
    rekordbox_id: str | None,
    file_path: str | None,
) -> ET.Element | None:
    root = tree.getroot()
    collection = root.find("COLLECTION")
    if collection is None:
        return None
    normalized_file_path = str(Path(file_path).expanduser()) if file_path else None
    for track_node in collection.findall("TRACK"):
        if rekordbox_id and track_node.attrib.get("TrackID") == rekordbox_id:
            return track_node
        if normalized_file_path:
            location = _parse_rekordbox_location(track_node.attrib.get("Location", ""))
            if location == normalized_file_path:
                return track_node
    return None


def _export_rekordbox_xml(
    session: Session,
    *,
    batch_id: str,
    export_job: JobRun,
    dry_run: bool,
) -> int:
    rows = _approved_metadata_rows_for_batch(session, batch_id)
    by_xml_path: dict[Path, list[ApprovedMetadata]] = defaultdict(list)
    for approved, _candidate, _raw_result in rows:
        xml_path = _track_rekordbox_xml_path(session, approved.track_id)
        if xml_path is not None:
            by_xml_path[xml_path].append(approved)

    writes = 0
    for xml_path, approved_rows in by_xml_path.items():
        tree = ET.parse(xml_path)
        dirty = False

        for approved in approved_rows:
            if approved.field_name not in REKORDBOX_TESTED_FIELDS:
                logger.warning("Skipping untested Rekordbox field write: %s", approved.field_name)
                _write_export_log(
                    session,
                    job_run_id=export_job.id,
                    track_id=approved.track_id,
                    target="rekordbox_xml",
                    field_name=approved.field_name,
                    old_value=None,
                    new_value=approved.value_json,
                    status="skipped_untested",
                )
                continue

            rekordbox_id, file_path = _track_rekordbox_identity(session, approved.track_id)
            track_node = _find_rekordbox_track_node(
                tree,
                rekordbox_id=rekordbox_id,
                file_path=file_path,
            )
            if track_node is None:
                _write_export_log(
                    session,
                    job_run_id=export_job.id,
                    track_id=approved.track_id,
                    target="rekordbox_xml",
                    field_name=approved.field_name,
                    old_value=None,
                    new_value=approved.value_json,
                    status="missing_track",
                )
                continue

            attr_name = REKORDBOX_XML_FIELD_MAP[approved.field_name]
            old_value = track_node.attrib.get(attr_name)
            new_value = _stringify_export_value(approved.value_json)
            if not dry_run:
                track_node.attrib[attr_name] = new_value
                dirty = True
            _write_export_log(
                session,
                job_run_id=export_job.id,
                track_id=approved.track_id,
                target="rekordbox_xml",
                field_name=approved.field_name,
                old_value=old_value,
                new_value=approved.value_json,
                status="preview" if dry_run else "written",
            )
            writes += 1

        if dirty and not dry_run:
            tree.write(xml_path, encoding="utf-8", xml_declaration=True)

    return writes


def _preferred_track_file(session: Session, track_id: str) -> TrackFile | None:
    preferred = session.scalar(
        select(TrackFile).where(
            TrackFile.track_id == track_id,
            TrackFile.active.is_(True),
            TrackFile.is_preferred.is_(True),
        )
    )
    if preferred is not None:
        return preferred
    return session.scalar(
        select(TrackFile).where(
            TrackFile.track_id == track_id,
            TrackFile.active.is_(True),
        )
    )


def _write_file_tag(file_path: Path, field_name: str, value: Any) -> Any:
    from mutagen import File as MutagenFile  # type: ignore

    tag_key = _FILE_TAG_FIELD_MAP.get(field_name)
    if tag_key is None:
        raise RuntimeError(f"Unsupported file tag field: {field_name}")

    audio = MutagenFile(file_path, easy=True)
    if audio is None:
        raise RuntimeError(f"mutagen could not open file: {file_path}")

    old_value = audio.get(tag_key)
    audio[tag_key] = [_stringify_export_value(value)]
    audio.save()
    return old_value


def _export_file_tags(
    session: Session,
    *,
    batch_id: str,
    export_job: JobRun,
    dry_run: bool,
) -> int:
    writes = 0
    for approved, _candidate, _raw_result in _approved_metadata_rows_for_batch(session, batch_id):
        if approved.field_name not in _FILE_TAG_FIELD_MAP:
            logger.warning("Skipping unsupported file-tag field write: %s", approved.field_name)
            _write_export_log(
                session,
                job_run_id=export_job.id,
                track_id=approved.track_id,
                target="file_tags",
                field_name=approved.field_name,
                old_value=None,
                new_value=approved.value_json,
                status="skipped_unsupported",
            )
            continue

        track_file = _preferred_track_file(session, approved.track_id)
        if track_file is None:
            _write_export_log(
                session,
                job_run_id=export_job.id,
                track_id=approved.track_id,
                target="file_tags",
                field_name=approved.field_name,
                old_value=None,
                new_value=approved.value_json,
                status="missing_file",
            )
            continue

        old_value = None
        if not dry_run:
            old_value = _write_file_tag(Path(track_file.path), approved.field_name, approved.value_json)
        _write_export_log(
            session,
            job_run_id=export_job.id,
            track_id=approved.track_id,
            target="file_tags",
            field_name=approved.field_name,
            old_value=old_value,
            new_value=approved.value_json,
            status="preview" if dry_run else "written",
        )
        writes += 1
    return writes


def run_tag_export(
    target: str,
    job_id_or_last: str,
    *,
    dry_run: bool = False,
    db_url: str | None = None,
) -> JobRun:
    session_factory = _session_factory(db_url)

    with session_factory() as session:
        fetch_job = _resolve_fetch_job(session, job_id_or_last)
        batch_id = _resolve_batch_id_for_fetch_job(session, fetch_job)
        export_job = _create_job_run(session, job_type="tag_export", dry_run=dry_run)

        if target == "rekordbox_xml":
            writes = _export_rekordbox_xml(
                session,
                batch_id=batch_id,
                export_job=export_job,
                dry_run=dry_run,
            )
        elif target == "file_tags":
            writes = _export_file_tags(
                session,
                batch_id=batch_id,
                export_job=export_job,
                dry_run=dry_run,
            )
        else:
            raise click.ClickException(f"Unsupported export target: {target}")

        export_job.status = "dry_run" if dry_run else "completed"
        export_job.finished_at = _utcnow()
        record_audit_event(
            session,
            export_job.id,
            "export",
            fetch_job.id,
            "tag_export",
            {
                "batch_id": batch_id,
                "target": target,
                "writes": writes,
                "dry_run": dry_run,
            },
        )
        session.commit()
        return export_job


def _library_db_sqlite_path(db_url: str | None = None) -> str:
    resolved = resolve_library_db_url(db_url or _default_db_url())
    url = make_url(resolved)
    if url.drivername != "sqlite":
        raise click.ClickException("tag sync-to-files only supports SQLite library databases")
    database = url.database
    if not database:
        raise click.ClickException("Could not resolve SQLite database path for tag sync-to-files")
    if database == ":memory:":
        raise click.ClickException("tag sync-to-files requires a file-backed SQLite library database")
    return str(database)


def _approved_metadata_rows_for_sync(
    session: Session,
    *,
    batch_id: str | None = None,
) -> list[tuple[ApprovedMetadata, str | None]]:
    statement = (
        select(ApprovedMetadata, RawProviderResult.provider)
        .outerjoin(
            MetadataCandidate,
            MetadataCandidate.id == ApprovedMetadata.approved_from_candidate_id,
        )
        .outerjoin(
            RawProviderResult,
            RawProviderResult.id == MetadataCandidate.raw_result_id,
        )
        .where(ApprovedMetadata.track_id.is_not(None))
        .order_by(ApprovedMetadata.track_id.asc(), ApprovedMetadata.field_name.asc())
    )
    if batch_id is not None:
        statement = statement.where(
            ApprovedMetadata.track_id.in_(
                select(SourceProvenance.track_id).where(
                    SourceProvenance.track_id.is_not(None),
                    SourceProvenance.source_type.in_(_BATCH_SOURCE_TYPES),
                    SourceProvenance.source_key == batch_id,
                )
            )
        )
    return list(session.execute(statement).all())


def _active_track_file_paths(
    session: Session,
    track_ids: set[str],
) -> dict[str, list[str]]:
    if not track_ids:
        return {}

    rows = session.execute(
        select(TrackFile.track_id, TrackFile.path)
        .where(
            TrackFile.track_id.in_(track_ids),
            TrackFile.active.is_(True),
        )
        .order_by(TrackFile.track_id.asc(), TrackFile.path.asc())
    ).all()
    paths_by_track_id: dict[str, list[str]] = defaultdict(list)
    for track_id, path in rows:
        if track_id is None or not path:
            continue
        if path not in paths_by_track_id[track_id]:
            paths_by_track_id[track_id].append(str(path))
    return dict(paths_by_track_id)


def _format_sync_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_enrichment_providers(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []

    if isinstance(raw_value, str):
        value = raw_value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            items = parsed
        else:
            items = value.split(",")
    elif isinstance(raw_value, list):
        items = raw_value
    else:
        items = [raw_value]

    providers: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if text in seen:
            continue
        providers.append(text)
        seen.add(text)
    return providers


def _append_enrichment_provider(existing: Any, provider_name: str | None) -> str | None:
    providers = _parse_enrichment_providers(existing)
    if provider_name:
        provider_text = provider_name.strip()
        if provider_text and provider_text not in providers:
            providers.append(provider_text)
    if not providers:
        return None
    return ",".join(providers)


def _library_track_keys_for_paths(
    conn: sqlite3.Connection,
    paths: list[str],
) -> list[str]:
    if not paths:
        return []

    placeholders = ",".join("?" for _ in paths)
    rows = conn.execute(
        f"""
        SELECT DISTINCT library_track_key
        FROM files
        WHERE path IN ({placeholders})
          AND library_track_key IS NOT NULL
          AND TRIM(library_track_key) != ''
        ORDER BY library_track_key
        """,
        paths,
    ).fetchall()
    return [str(row["library_track_key"]) for row in rows if row["library_track_key"]]


def _resolve_target_files_for_track(
    conn: sqlite3.Connection,
    track_id: str,
    source_paths: list[str],
) -> list[dict[str, Any]]:
    if not source_paths:
        logger.info("No active track files found for track %s; skipping sync-to-files", track_id)
        return []

    keys = _library_track_keys_for_paths(conn, source_paths)
    if not keys:
        logger.info(
            "No matching files rows with library_track_key found for track %s; paths=%s",
            track_id,
            ", ".join(source_paths),
        )
        return []

    files_by_path: dict[str, dict[str, Any]] = {}
    for library_track_key in keys:
        for row in get_files_for_library_track(conn, library_track_key):
            files_by_path[str(row["path"])] = dict(row)

    if not files_by_path:
        logger.info(
            "No files rows found for track %s after resolving library_track_key(s): %s",
            track_id,
            ", ".join(keys),
        )
        return []

    return [files_by_path[path] for path in sorted(files_by_path)]


def _sync_updates_for_approved_metadata(
    approved: ApprovedMetadata,
    summary: _SyncToFilesSummary,
) -> dict[str, Any] | None:
    value = approved.value_json
    if value is None:
        summary.skipped_null_source += 1
        return None

    if approved.field_name == "canonical_key":
        normalized = normalize_key(str(value))
        if normalized is None:
            logger.warning(
                "Skipping canonical_key sync for track %s: unrecognized key %r",
                approved.track_id,
                value,
            )
            summary.warnings += 1
            return None

        updates = {"canonical_key": normalized}
        camelot = classical_to_camelot(normalized)
        if camelot is not None:
            updates["key_camelot"] = camelot
        return updates

    columns = _SYNC_FIELD_COLUMN_MAP.get(approved.field_name)
    if columns is None:
        logger.warning("Skipping unsupported approved_metadata field: %s", approved.field_name)
        summary.warnings += 1
        return None

    if approved.field_name == "canonical_explicit" and isinstance(value, bool):
        value = 1 if value else 0

    return {column: value for column in columns}


def _write_sync_update(
    conn: sqlite3.Connection,
    *,
    path: str,
    column_updates: dict[str, Any],
    enriched_at: str,
    enrichment_providers: str | None,
) -> None:
    assignments = [f"{column} = ?" for column in column_updates]
    params: list[Any] = list(column_updates.values())
    assignments.append("enriched_at = ?")
    params.append(enriched_at)
    assignments.append("enrichment_providers = ?")
    params.append(enrichment_providers)
    params.append(path)
    conn.execute(
        f"UPDATE files SET {', '.join(assignments)} WHERE path = ?",
        params,
    )


def _sync_summary_line(summary: _SyncToFilesSummary) -> str:
    return (
        f"Sync complete: {len(summary.files_updated)} files updated, "
        f"{summary.fields_written} fields written, "
        f"{summary.skipped_null_source} skipped (null source), "
        f"{summary.skipped_already_set} skipped (already set), "
        f"{summary.warnings} warnings"
    )


def run_tag_sync_to_files(
    *,
    batch_id: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    db_url: str | None = None,
) -> _SyncToFilesSummary:
    session_factory = _session_factory(db_url)
    db_path = _library_db_sqlite_path(db_url)
    summary = _SyncToFilesSummary()
    sync_timestamp = _utcnow().isoformat()

    with session_factory() as session, sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        init_db(conn)

        approved_rows = _approved_metadata_rows_for_sync(session, batch_id=batch_id)
        track_ids = {approved.track_id for approved, _provider_name in approved_rows if approved.track_id}
        paths_by_track_id = _active_track_file_paths(session, track_ids)
        target_files_by_track_id = {
            track_id: _resolve_target_files_for_track(conn, track_id, source_paths)
            for track_id, source_paths in paths_by_track_id.items()
        }

        for approved, provider_name in approved_rows:
            if approved.track_id is None:
                continue

            column_updates = _sync_updates_for_approved_metadata(approved, summary)
            if not column_updates:
                continue

            target_files = target_files_by_track_id.get(approved.track_id)
            if not target_files:
                logger.info(
                    "No matching files rows found for approved metadata track %s field %s",
                    approved.track_id,
                    approved.field_name,
                )
                continue

            for file_row in target_files:
                file_path = str(file_row["path"])
                pending_updates: dict[str, Any] = {}
                for column, new_value in column_updates.items():
                    old_value = file_row.get(column)
                    if old_value is not None and not force:
                        summary.skipped_already_set += 1
                        continue
                    pending_updates[column] = new_value
                    if dry_run:
                        click.echo(
                            f"{file_path}: {column}: "
                            f"{_format_sync_value(old_value)} -> {_format_sync_value(new_value)}"
                        )

                if not pending_updates:
                    continue

                enrichment_providers = _append_enrichment_provider(
                    file_row.get("enrichment_providers"),
                    provider_name,
                )
                if not dry_run:
                    _write_sync_update(
                        conn,
                        path=file_path,
                        column_updates=pending_updates,
                        enriched_at=sync_timestamp,
                        enrichment_providers=enrichment_providers,
                    )

                file_row.update(pending_updates)
                file_row["enriched_at"] = sync_timestamp
                file_row["enrichment_providers"] = enrichment_providers
                summary.files_updated.add(file_path)
                summary.fields_written += len(pending_updates)

    click.echo(_sync_summary_line(summary))
    return summary


def _latest_existing_cohort(
    conn: sqlite3.Connection,
    *,
    source_url: str,
) -> sqlite3.Row | tuple[Any, ...] | None:
    rows = find_cohort_by_source(conn, source_url=source_url, blocked_only=False)
    return rows[0] if rows else None


def _cohort_flac_paths(conn: sqlite3.Connection, *, cohort_id: int) -> list[Path]:
    return [path for path in cohort_paths(conn, cohort_id=cohort_id) if path.suffix.lower() == ".flac"]


def _run_retag_flow(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    cohort_id: int,
    flac_paths: list[Path],
    placeholder_source: str,
    dj: bool,
    force: bool,
) -> tuple[bool, str | None]:
    if not flac_paths:
        return False, "no FLAC files found for retag"

    retag_result = retag_flac_paths(db_path=db_path, flac_paths=flac_paths, force=force)
    mark_paths_ok(conn, cohort_id=cohort_id, paths=retag_result.ok_paths)

    for path, reason in retag_result.blocked.items():
        asset_row = conn.execute(
            "SELECT id FROM asset_file WHERE path = ? LIMIT 1",
            (str(path),),
        ).fetchone()
        asset_file_id = int(asset_row[0]) if asset_row is not None and asset_row[0] is not None else None
        mark_cohort_file_blocked(
            conn,
            cohort_id=cohort_id,
            stage="enrich",
            reason=reason,
            source_path=str(path),
            asset_file_id=asset_file_id,
        )

    if retag_result.blocked:
        set_cohort_blocked(
            conn,
            cohort_id=cohort_id,
            reason=f"{len(retag_result.blocked)} file(s) failed during enrich",
        )
        return False, "one or more files failed during enrich"

    output_result = build_output_artifacts(
        db_path=db_path,
        cohort_id=cohort_id,
        flac_paths=retag_result.ok_paths,
        dj=dj,
        playlist_only=False,
    )
    if not output_result.ok:
        record_blocked_paths(
            conn,
            cohort_id=cohort_id,
            stage=output_result.stage or "output",
            reason=output_result.reason or "output failed",
            paths=retag_result.ok_paths,
            placeholder_source=placeholder_source,
        )
        return False, output_result.reason

    refresh_cohort_status(conn, cohort_id=cohort_id)
    return True, None


def register_curate_group(parent: click.Group) -> None:
    @parent.group("curate")
    def curate():  # type: ignore[misc]
        """Staged metadata fetch, review, apply, and export workflows."""

    @curate.command("fetch")
    @click.option("--provider", "provider_name", required=True, help="Registered metadata provider name")
    @click.option("--batch", "batch_id", required=True, help="Batch identifier")
    @click.option("--dry-run", is_flag=True, help="Preview provider work without storing candidates")
    def tag_fetch_command(provider_name: str, batch_id: str, dry_run: bool) -> None:  # type: ignore[misc]
        job_run = run_tag_fetch(provider_name, batch_id, dry_run=dry_run)
        click.echo(f"Job: {job_run.id}")
        click.echo(f"Status: {job_run.status}")

    @curate.command("batch-create")
    @click.option("--source", required=True, help="Batch source type")
    @click.option("--playlist-id", required=True, help="Playlist identifier")
    @click.option("--batch", "batch_id", required=True, help="Batch identifier")
    def tag_batch_create_command(source: str, playlist_id: str, batch_id: str) -> None:  # type: ignore[misc]
        queued = run_tag_batch_create(source, playlist_id, batch_id)
        click.echo(f"Created batch {batch_id}: {queued} tracks queued.")

    @curate.command("review")
    @click.option("--batch", "batch_id", required=True, help="Batch identifier")
    def tag_review_command(batch_id: str) -> None:  # type: ignore[misc]
        reviewed = run_tag_review(batch_id)
        click.echo(f"Reviewed groups: {reviewed}")

    @curate.command("apply")
    @click.option("--batch", "batch_id", required=True, help="Batch identifier")
    def tag_apply_command(batch_id: str) -> None:  # type: ignore[misc]
        job_run = run_tag_apply(batch_id)
        click.echo(f"Job: {job_run.id}")
        click.echo(f"Status: {job_run.status}")

    @curate.command("export")
    @click.option(
        "--target",
        required=True,
        type=click.Choice(["rekordbox_xml", "file_tags"], case_sensitive=False),
        help="Export target",
    )
    @click.option("--job", "job_id_or_last", required=True, help="Source fetch job id or 'last'")
    @click.option("--dry-run", is_flag=True, help="Preview export writes without touching files")
    def tag_export_command(target: str, job_id_or_last: str, dry_run: bool) -> None:  # type: ignore[misc]
        job_run = run_tag_export(target, job_id_or_last, dry_run=dry_run)
        click.echo(f"Job: {job_run.id}")
        click.echo(f"Status: {job_run.status}")

    @curate.command("sync-to-files")
    @click.option("--batch", "batch_id", help="Restrict sync to a specific tag batch")
    @click.option("--dry-run", is_flag=True, help="Preview file-table writes without updating files")
    @click.option("--force", is_flag=True, help="Overwrite non-NULL file-table values")
    def tag_sync_to_files_command(batch_id: str | None, dry_run: bool, force: bool) -> None:  # type: ignore[misc]
        run_tag_sync_to_files(batch_id=batch_id, dry_run=dry_run, force=force)


def register_tag_group(cli: click.Group) -> None:
    @cli.command("tag", help="Curate, fetch, apply, and sync metadata tags for library files.")
    @click.argument("target", required=False)
    @click.option("--db", "db_path_arg", type=click.Path(), help="Database path (or TAGSLUT_DB)")
    @click.option("--all", "tag_all", is_flag=True, help="Retag the full library.")
    @click.option("--dj", is_flag=True, help="Rebuild DJ MP3 output for the targeted cohort.")
    @click.option("--fix", "fix_mode", is_flag=True, help="Clear blocked state on success for post-download cohorts.")
    def tag_command(  # type: ignore[misc]
        target: str | None,
        db_path_arg: str | None,
        tag_all: bool,
        dj: bool,
        fix_mode: bool,
    ) -> None:
        if tag_all and target:
            raise click.ClickException("Use a target or --all, not both.")
        if not tag_all and not target:
            raise click.ClickException("Provide a local path, a cohort URL, or use --all.")
        if fix_mode and tag_all:
            raise click.ClickException("--fix requires a specific local path or cohort URL target.")

        try:
            resolution = resolve_cli_env_db_path(db_path_arg, purpose="write", source_label="--db")
        except DbResolutionError as exc:
            raise click.ClickException(str(exc)) from exc
        db_path = resolution.path

        with sqlite3.connect(str(db_path)) as conn:
            ensure_cohort_support(conn)

            if tag_all:
                library_root = get_library_volume().expanduser().resolve()
                cohort_id = create_cohort(
                    conn,
                    source_url=str(library_root),
                    source_kind="local_path",
                    flags={"command": "tag", "dj": bool(dj)},
                )
                flac_paths = resolve_flac_paths(library_root)
                ok, reason = _run_retag_flow(
                    conn,
                    db_path=db_path,
                    cohort_id=cohort_id,
                    flac_paths=flac_paths,
                    placeholder_source=str(library_root),
                    dj=dj,
                    force=False,
                )
                conn.commit()
                if not ok and reason:
                    click.echo(reason, err=True)
                raise SystemExit(0 if ok else 2)

            assert target is not None
            if target.startswith("http://") or target.startswith("https://"):
                source_url = target.strip()
                if fix_mode:
                    blocked_row, ambiguous = find_latest_blocked_cohort_for_source(conn, source_url=source_url)
                    if blocked_row is None:
                        raise click.ClickException(f"No blocked cohort exists for URL: {source_url}")
                    if ambiguous:
                        raise click.ClickException(
                            "Multiple blocked cohorts match this exact URL. Use `tagslut fix <cohort_id>`."
                        )
                    cohort_id = int(blocked_row[0])
                    blocked_stages = {
                        str(row[6])
                        for row in blocked_rows_for_cohort(conn, cohort_id=cohort_id)
                        if row[6] is not None
                    }
                    if any(stage in EARLY_BLOCKED_STAGES for stage in blocked_stages):
                        raise click.ClickException(
                            "Cohort is blocked at download/acquisition stage. Use `tagslut fix <cohort_id>` or `tagslut get <url> --fix`."
                        )
                    set_cohort_running(conn, cohort_id=cohort_id)
                    flac_paths = _cohort_flac_paths(conn, cohort_id=cohort_id)
                    ok, reason = _run_retag_flow(
                        conn,
                        db_path=db_path,
                        cohort_id=cohort_id,
                        flac_paths=flac_paths,
                        placeholder_source=source_url,
                        dj=dj,
                        force=True,
                    )
                    conn.commit()
                    if not ok and reason:
                        click.echo(reason, err=True)
                    raise SystemExit(0 if ok else 2)

                latest = _latest_existing_cohort(conn, source_url=source_url)
                if latest is None:
                    raise click.ClickException(f"No cohort exists for URL: {source_url}")
                if str(latest[3]) == "blocked":
                    click.echo(
                        cohort_requires_fix_message(
                            cohort_id=int(latest[0]),
                            source_url=str(latest[1]) if latest[1] is not None else None,
                        ),
                        err=True,
                    )
                cohort_id = int(latest[0])
                flac_paths = _cohort_flac_paths(conn, cohort_id=cohort_id)
                ok, reason = _run_retag_flow(
                    conn,
                    db_path=db_path,
                    cohort_id=cohort_id,
                    flac_paths=flac_paths,
                    placeholder_source=source_url,
                    dj=dj,
                    force=False,
                )
                conn.commit()
                if not ok and reason:
                    click.echo(reason, err=True)
                raise SystemExit(0 if ok else 2)

            target_path = Path(target).expanduser().resolve()
            if not target_path.exists():
                raise click.ClickException(f"Path not found: {target_path}")

            source_url = str(target_path)
            if fix_mode:
                blocked_row, ambiguous = find_latest_blocked_cohort_for_source(conn, source_url=source_url)
                if blocked_row is None:
                    raise click.ClickException(f"No blocked cohort exists for: {source_url}")
                if ambiguous:
                    raise click.ClickException(
                        "Multiple blocked cohorts match this local path. Use `tagslut fix <cohort_id>`."
                    )
                cohort_id = int(blocked_row[0])
                blocked_stages = {
                    str(row[6])
                    for row in blocked_rows_for_cohort(conn, cohort_id=cohort_id)
                    if row[6] is not None
                }
                if any(stage in EARLY_BLOCKED_STAGES for stage in blocked_stages):
                    raise click.ClickException(
                        "Cohort is blocked at download/acquisition stage. Use `tagslut fix <cohort_id>`."
                    )
                set_cohort_running(conn, cohort_id=cohort_id)
                flac_paths = _cohort_flac_paths(conn, cohort_id=cohort_id) or resolve_flac_paths(target_path)
                ok, reason = _run_retag_flow(
                    conn,
                    db_path=db_path,
                    cohort_id=cohort_id,
                    flac_paths=flac_paths,
                    placeholder_source=source_url,
                    dj=dj,
                    force=True,
                )
                conn.commit()
                if not ok and reason:
                    click.echo(reason, err=True)
                raise SystemExit(0 if ok else 2)

            blocked_row, ambiguous = find_latest_blocked_cohort_for_source(conn, source_url=source_url)
            if blocked_row is not None and not ambiguous:
                click.echo(
                    cohort_requires_fix_message(
                        cohort_id=int(blocked_row[0]),
                        source_url=str(blocked_row[1]) if blocked_row[1] is not None else None,
                    ),
                    err=True,
                )
            cohort_id = create_cohort(
                conn,
                source_url=source_url,
                source_kind="local_path",
                flags={"command": "tag", "dj": bool(dj)},
            )
            flac_paths = resolve_flac_paths(target_path)
            ok, reason = _run_retag_flow(
                conn,
                db_path=db_path,
                cohort_id=cohort_id,
                flac_paths=flac_paths,
                placeholder_source=source_url,
                dj=dj,
                force=False,
            )
            conn.commit()
            if not ok and reason:
                click.echo(reason, err=True)
            raise SystemExit(0 if ok else 2)
