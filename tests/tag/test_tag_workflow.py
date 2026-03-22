from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tagslut.adapters.rekordbox.importer import import_rekordbox_xml
from tagslut.cli.commands.tag import run_tag_apply, run_tag_export, run_tag_fetch
from tagslut.library import create_library_engine, ensure_library_schema
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
)
from tagslut.library.repositories import record_audit_event
from tagslut.tag.providers import clear_provider_registry, register_provider
from tagslut.tag.providers.base import FieldCandidate, RawResult

FIXTURE_XML = Path(__file__).resolve().parents[1] / "library" / "fixtures" / "small_rekordbox.xml"


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'tagging.db').resolve()}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _copy_fixture_xml(tmp_path: Path) -> Path:
    xml_path = tmp_path / "small_rekordbox.xml"
    xml_path.write_text(FIXTURE_XML.read_text(encoding="utf-8"), encoding="utf-8")
    return xml_path


def _count(session: Session, model: type[object]) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _batch_membership(session: Session, batch_id: str) -> None:
    tracks = list(session.scalars(select(Track)))
    for track in tracks:
        session.add(
            SourceProvenance(
                track_id=track.id,
                source_type="tag_batch",
                source_key=batch_id,
            )
        )
    session.commit()


def _prepare_library(tmp_path: Path, batch_id: str = "batch-1") -> tuple[str, Path]:
    db_url = _db_url(tmp_path)
    xml_path = _copy_fixture_xml(tmp_path)
    result = import_rekordbox_xml(xml_path, db_url, dry_run=False)
    assert result.errors == []
    ensure_library_schema(db_url)
    engine = create_library_engine(db_url)
    with Session(engine) as session:
        _batch_membership(session, batch_id)
    return db_url, xml_path


def _field(
    field_name: str,
    value: Any,
    confidence: float,
    *,
    rationale: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "value": value,
        "confidence": confidence,
        "rationale": rationale or {"source": "test"},
    }


class StubProvider:
    def __init__(self, name: str, results_by_title: dict[str, list[dict[str, Any]]]):
        self.name = name
        self._results_by_title = results_by_title
        self.calls: list[str] = []

    def search(self, query) -> list[RawResult]:  # type: ignore[no-untyped-def]
        self.calls.append(query.title)
        rows = self._results_by_title.get(query.title, [])
        return [
            RawResult(
                provider=self.name,
                external_id=row.get("external_id"),
                query_text=row.get("query_text", f"{query.artist} - {query.title}"),
                payload={"fields": row.get("fields", [])},
            )
            for row in rows
        ]

    def normalize(self, raw: RawResult) -> list[FieldCandidate]:
        return [
            FieldCandidate(
                field_name=str(field["field_name"]),
                normalized_value=field["value"],
                confidence=float(field["confidence"]),
                rationale=dict(field.get("rationale", {})),
            )
            for field in raw.payload["fields"]
        ]


def _seed_fetch_job(session: Session, batch_id: str) -> str:
    job_run = JobRun(
        job_type="tag_fetch",
        dry_run=False,
        status="completed",
        started_at=_utcnow(),
        finished_at=_utcnow(),
    )
    session.add(job_run)
    session.flush()
    record_audit_event(
        session,
        job_run.id,
        "batch",
        batch_id,
        "tag_fetch_complete",
        {"batch_id": batch_id},
    )
    session.commit()
    return str(job_run.id)


@pytest.fixture(autouse=True)
def _provider_registry() -> Iterator[None]:
    clear_provider_registry()
    yield
    clear_provider_registry()


def test_fetch_dry_run_no_commit(tmp_path: Path) -> None:
    batch_id = "batch-dry-run"
    db_url, _xml_path = _prepare_library(tmp_path, batch_id=batch_id)
    provider = StubProvider(
        "stub",
        {
            "First Track": [{"fields": [_field("comments", "Preview comment", 0.95)]}],
            "Second Track": [{"fields": [_field("comments", "Preview comment 2", 0.94)]}],
        },
    )
    register_provider(provider)

    job_run = run_tag_fetch(provider.name, batch_id, dry_run=True, db_url=db_url)

    assert job_run.dry_run is True
    assert job_run.status == "dry_run"
    assert provider.calls == ["First Track", "Second Track"]

    engine = create_library_engine(db_url)
    with Session(engine) as session:
        assert _count(session, RawProviderResult) == 0
        assert _count(session, MetadataCandidate) == 0
        assert _count(session, MatchCandidate) == 0
        assert _count(session, JobRun) == 2
        assert _count(session, AuditEvent) == 5


def test_fetch_creates_candidates(tmp_path: Path) -> None:
    batch_id = "batch-fetch"
    db_url, _xml_path = _prepare_library(tmp_path, batch_id=batch_id)
    provider = StubProvider(
        "stub",
        {
            "First Track": [
                {
                    "fields": [
                        _field("comments", "Peak time weapon", 0.95),
                        _field("bpm", 128, 0.97),
                    ]
                }
            ],
            "Second Track": [{"fields": [_field("comments", "Warmup option", 0.92)]}],
        },
    )
    register_provider(provider)

    job_run = run_tag_fetch(provider.name, batch_id, dry_run=False, db_url=db_url)

    assert job_run.status == "completed"

    engine = create_library_engine(db_url)
    with Session(engine) as session:
        assert _count(session, RawProviderResult) == 2
        assert _count(session, MetadataCandidate) == 3
        assert _count(session, MatchCandidate) == 2
        assert {row.batch_id for row in session.scalars(select(RawProviderResult))} == {batch_id}


def test_apply_upserts_approved_metadata(tmp_path: Path) -> None:
    batch_id = "batch-apply"
    db_url, _xml_path = _prepare_library(tmp_path, batch_id=batch_id)
    provider = StubProvider(
        "stub",
        {
            "First Track": [{"fields": [_field("comments", "Peak time weapon", 0.95)]}],
            "Second Track": [],
        },
    )
    register_provider(provider)

    run_tag_fetch(provider.name, batch_id, dry_run=False, db_url=db_url)
    run_tag_apply(batch_id, db_url=db_url)

    engine = create_library_engine(db_url)
    with Session(engine) as session:
        approved = list(
            session.scalars(
                select(ApprovedMetadata).where(ApprovedMetadata.field_name == "comments")
            )
        )
        assert len(approved) == 1
        assert approved[0].value_json == "Peak time weapon"
        assert approved[0].approved_from_candidate_id is not None


def test_apply_respects_user_override(tmp_path: Path) -> None:
    batch_id = "batch-override"
    db_url, _xml_path = _prepare_library(tmp_path, batch_id=batch_id)
    engine = create_library_engine(db_url)

    with Session(engine) as session:
        track = session.scalar(select(Track).where(Track.canonical_title == "First Track"))
        assert track is not None

        raw_result = RawProviderResult(
            batch_id=batch_id,
            provider="stub",
            external_id=None,
            query_text="Alpha Artist - First Track",
            payload_json={},
            fetched_at=_utcnow(),
        )
        session.add(raw_result)
        session.flush()

        auto_candidate = MetadataCandidate(
            track_id=track.id,
            raw_result_id=raw_result.id,
            field_name="comments",
            normalized_value_json="Auto Value",
            confidence=0.98,
            rationale_json={"approved_by": "auto"},
            status="approved",
            is_user_override=False,
        )
        override_candidate = MetadataCandidate(
            track_id=track.id,
            raw_result_id=raw_result.id,
            field_name="comments",
            normalized_value_json="Manual Value",
            confidence=1.0,
            rationale_json={"approved_by": "tester"},
            status="approved",
            is_user_override=True,
        )
        session.add_all([auto_candidate, override_candidate])
        session.flush()
        session.add(
            ApprovedMetadata(
                track_id=track.id,
                field_name="comments",
                value_json="Existing Value",
                approved_by="seed",
                approved_at=_utcnow(),
                is_user_override=False,
            )
        )
        session.commit()

    run_tag_apply(batch_id, db_url=db_url)

    with Session(engine) as session:
        approved = session.scalar(
            select(ApprovedMetadata).where(ApprovedMetadata.field_name == "comments")
        )
        assert approved is not None
        assert approved.value_json == "Manual Value"
        assert approved.is_user_override is True


def test_export_rekordbox_skips_untested_fields(tmp_path: Path) -> None:
    batch_id = "batch-export-skip"
    db_url, xml_path = _prepare_library(tmp_path, batch_id=batch_id)
    engine = create_library_engine(db_url)

    with Session(engine) as session:
        fetch_job_id = _seed_fetch_job(session, batch_id)
        track = session.scalar(select(Track).where(Track.canonical_title == "First Track"))
        assert track is not None

        raw_result = RawProviderResult(
            batch_id=batch_id,
            provider="stub",
            external_id=None,
            query_text="Alpha Artist - First Track",
            payload_json={},
            fetched_at=_utcnow(),
        )
        session.add(raw_result)
        session.flush()
        candidate = MetadataCandidate(
            track_id=track.id,
            raw_result_id=raw_result.id,
            field_name="genre",
            normalized_value_json="Techno",
            confidence=1.0,
            rationale_json={},
            status="approved",
            is_user_override=False,
        )
        session.add(candidate)
        session.flush()
        session.add(
            ApprovedMetadata(
                track_id=track.id,
                field_name="genre",
                value_json="Techno",
                approved_from_candidate_id=candidate.id,
                approved_by="tester",
                approved_at=_utcnow(),
                is_user_override=False,
            )
        )
        session.commit()

    before = xml_path.read_text(encoding="utf-8")
    run_tag_export("rekordbox_xml", fetch_job_id, dry_run=False, db_url=db_url)
    after = xml_path.read_text(encoding="utf-8")

    assert before == after

    with Session(engine) as session:
        log_row = session.scalar(
            select(ExportWriteLog).where(
                ExportWriteLog.target == "rekordbox_xml",
                ExportWriteLog.field_name == "genre",
            )
        )
        assert log_row is not None
        assert log_row.status == "skipped_untested"


def test_export_dry_run_writes_preview_log(tmp_path: Path) -> None:
    batch_id = "batch-export-preview"
    db_url, xml_path = _prepare_library(tmp_path, batch_id=batch_id)
    engine = create_library_engine(db_url)

    with Session(engine) as session:
        fetch_job_id = _seed_fetch_job(session, batch_id)
        track = session.scalar(select(Track).where(Track.canonical_title == "First Track"))
        assert track is not None

        raw_result = RawProviderResult(
            batch_id=batch_id,
            provider="stub",
            external_id=None,
            query_text="Alpha Artist - First Track",
            payload_json={},
            fetched_at=_utcnow(),
        )
        session.add(raw_result)
        session.flush()
        candidate = MetadataCandidate(
            track_id=track.id,
            raw_result_id=raw_result.id,
            field_name="canonical_title",
            normalized_value_json="Preview Title",
            confidence=1.0,
            rationale_json={},
            status="approved",
            is_user_override=False,
        )
        session.add(candidate)
        session.flush()
        session.add(
            ApprovedMetadata(
                track_id=track.id,
                field_name="canonical_title",
                value_json="Preview Title",
                approved_from_candidate_id=candidate.id,
                approved_by="tester",
                approved_at=_utcnow(),
                is_user_override=False,
            )
        )
        session.commit()

    before = xml_path.read_text(encoding="utf-8")
    run_tag_export("rekordbox_xml", fetch_job_id, dry_run=True, db_url=db_url)
    after = xml_path.read_text(encoding="utf-8")

    assert before == after

    with Session(engine) as session:
        log_row = session.scalar(
            select(ExportWriteLog).where(
                ExportWriteLog.target == "rekordbox_xml",
                ExportWriteLog.field_name == "canonical_title",
            )
        )
        assert log_row is not None
        assert log_row.status == "preview"
        assert log_row.old_value_json == "First Track"
        assert log_row.new_value_json == "Preview Title"


def test_auto_approve_threshold(tmp_path: Path) -> None:
    batch_id = "batch-auto-approve"
    db_url, _xml_path = _prepare_library(tmp_path, batch_id=batch_id)
    provider = StubProvider(
        "stub",
        {
            "First Track": [
                {"fields": [_field("comments", "Peak time weapon", 0.96)]},
                {"fields": [_field("comments", "Warmup option", 0.70)]},
            ],
            "Second Track": [],
        },
    )
    register_provider(provider)

    run_tag_fetch(provider.name, batch_id, dry_run=False, db_url=db_url)

    engine = create_library_engine(db_url)
    with Session(engine) as session:
        track = session.scalar(select(Track).where(Track.canonical_title == "First Track"))
        assert track is not None

        candidates = list(
            session.scalars(
                select(MetadataCandidate).where(
                    MetadataCandidate.track_id == track.id,
                    MetadataCandidate.field_name == "comments",
                )
            )
        )
        assert len(candidates) == 2
        approved = [candidate for candidate in candidates if candidate.status == "approved"]
        assert len(approved) == 1
        assert approved[0].normalized_value_json == "Peak time weapon"


def test_provider_disagreement_forces_review(tmp_path: Path) -> None:
    batch_id = "batch-disagreement"
    db_url, _xml_path = _prepare_library(tmp_path, batch_id=batch_id)
    provider = StubProvider(
        "stub",
        {
            "First Track": [
                {"fields": [_field("canonical_title", "First Track", 0.99)]},
                {"fields": [_field("canonical_title", "First Track Alt", 0.60)]},
            ],
            "Second Track": [],
        },
    )
    register_provider(provider)

    run_tag_fetch(provider.name, batch_id, dry_run=False, db_url=db_url)

    engine = create_library_engine(db_url)
    with Session(engine) as session:
        track = session.scalar(select(Track).where(Track.canonical_title == "First Track"))
        assert track is not None

        candidates = list(
            session.scalars(
                select(MetadataCandidate).where(
                    MetadataCandidate.track_id == track.id,
                    MetadataCandidate.field_name == "canonical_title",
                )
            )
        )
        assert len(candidates) == 2
        assert {candidate.status for candidate in candidates} == {"pending"}
