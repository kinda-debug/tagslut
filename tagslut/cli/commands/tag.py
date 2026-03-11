from __future__ import annotations

import getpass
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

import click
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from tagslut.library import (
    DEFAULT_LIBRARY_DB_URL,
    create_library_session_factory,
    ensure_library_schema,
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
from tagslut.library.repositories import record_audit_event
from tagslut.tag.providers import get_provider
from tagslut.tag.providers.base import FieldCandidate, RawResult
from tagslut.tag.rekordbox_compat import REKORDBOX_TESTED_FIELDS, REKORDBOX_XML_FIELD_MAP
from tagslut.utils.config import get_config

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


@dataclass(frozen=True)
class _AutoApprovalDecision:
    winner_id: str | None
    status_by_candidate_id: dict[str, str]
    rationale_by_candidate_id: dict[str, dict[str, Any]]


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


def _tracks_for_batch(session: Session, batch_id: str) -> list[Track]:
    return list(
        session.scalars(
            select(Track)
            .join(SourceProvenance, SourceProvenance.track_id == Track.id)
            .where(
                Track.status == "active",
                SourceProvenance.source_type.in_(_BATCH_SOURCE_TYPES),
                SourceProvenance.source_key == batch_id,
            )
            .options(
                selectinload(Track.aliases),
                selectinload(Track.files),
            )
            .order_by(Track.created_at.asc())
        )
    )


def _build_track_query(track: Track) -> TrackQuery:
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
    track_id: str,
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
    grouped: dict[tuple[str | None, str], list[tuple[MetadataCandidate, RawProviderResult]]] = defaultdict(list)
    for candidate, raw_result in _candidate_rows_for_batch(session, batch_id):
        grouped[(candidate.track_id, candidate.field_name)].append((candidate, raw_result))

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
        tracks = _tracks_for_batch(session, batch_id)
        matcher = TrackMatcher(session)
        job_run = _create_job_run(session, job_type="tag_fetch", dry_run=dry_run)

        raw_result_count = 0
        metadata_candidate_count = 0
        match_candidate_count = 0

        for track in tracks:
            track_query = _build_track_query(track)
            raw_results = provider.search(track_query)
            track_raw_count = 0
            track_metadata_count = 0
            track_match_count = 0

            for raw_result in raw_results:
                field_candidates = provider.normalize(raw_result)
                match_result = matcher.match(
                    _match_query_for_raw(track_query, raw_result, field_candidates)
                )
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
                        track_id=track.id,
                        raw_result_id=raw_row.id,
                        field_candidate=field_candidate,
                    )

            raw_result_count += track_raw_count
            metadata_candidate_count += track_metadata_count
            match_candidate_count += track_match_count
            record_audit_event(
                session,
                job_run.id,
                "track",
                track.id,
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
                tracks_seen=len(tracks),
                raw_results=raw_result_count,
                metadata_candidates=metadata_candidate_count,
                match_candidates=match_candidate_count,
            ),
        )
        session.commit()
        return job_run


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


def run_tag_apply(batch_id: str, *, db_url: str | None = None) -> JobRun:
    session_factory = _session_factory(db_url)

    with session_factory() as session:
        _apply_auto_approval_rules(session, batch_id)
        job_run = _create_job_run(session, job_type="tag_apply", dry_run=False)

        for (track_id, field_name), candidates in _approved_candidate_groups(session, batch_id).items():
            winner = _choose_candidate_for_apply(candidates)
            existing = session.scalar(
                select(ApprovedMetadata).where(
                    ApprovedMetadata.track_id == track_id,
                    ApprovedMetadata.field_name == field_name,
                )
            )

            applied = False
            action = "skipped_existing"
            if existing is None:
                session.add(
                    ApprovedMetadata(
                        track_id=track_id,
                        field_name=field_name,
                        value_json=winner.normalized_value_json,
                        approved_from_candidate_id=winner.id,
                        approved_by=str(winner.rationale_json.get("approved_by") or "auto"),
                        approved_at=_utcnow(),
                        is_user_override=bool(winner.is_user_override),
                    )
                )
                applied = True
                action = "inserted"
            elif winner.is_user_override:
                existing.value_json = winner.normalized_value_json
                existing.approved_from_candidate_id = winner.id
                existing.approved_by = str(winner.rationale_json.get("approved_by") or "override")
                existing.approved_at = _utcnow()
                existing.is_user_override = True
                applied = True
                action = "overridden"

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


def register_tag_group(cli: click.Group) -> None:
    @cli.group()
    def tag():  # type: ignore[misc]
        """Staged metadata fetch, review, apply, and export workflows."""

    @tag.command("fetch")
    @click.option("--provider", "provider_name", required=True, help="Registered metadata provider name")
    @click.option("--batch", "batch_id", required=True, help="Batch identifier")
    @click.option("--dry-run", is_flag=True, help="Preview provider work without storing candidates")
    def tag_fetch_command(provider_name: str, batch_id: str, dry_run: bool) -> None:  # type: ignore[misc]
        job_run = run_tag_fetch(provider_name, batch_id, dry_run=dry_run)
        click.echo(f"Job: {job_run.id}")
        click.echo(f"Status: {job_run.status}")

    @tag.command("review")
    @click.option("--batch", "batch_id", required=True, help="Batch identifier")
    def tag_review_command(batch_id: str) -> None:  # type: ignore[misc]
        reviewed = run_tag_review(batch_id)
        click.echo(f"Reviewed groups: {reviewed}")

    @tag.command("apply")
    @click.option("--batch", "batch_id", required=True, help="Batch identifier")
    def tag_apply_command(batch_id: str) -> None:  # type: ignore[misc]
        job_run = run_tag_apply(batch_id)
        click.echo(f"Job: {job_run.id}")
        click.echo(f"Status: {job_run.status}")

    @tag.command("export")
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
