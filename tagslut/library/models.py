from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Release(Base):
    __tablename__ = "release"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    artist_credit: Mapped[str | None] = mapped_column(String(512))
    label: Mapped[str | None] = mapped_column(String(255))
    catalog_no: Mapped[str | None] = mapped_column(String(255))
    release_date: Mapped[date | None] = mapped_column(Date())

    tracks: Mapped[list["Track"]] = relationship(back_populates="canonical_release")


class Track(Base):
    __tablename__ = "track"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived', 'rejected')",
            name="ck_track_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    canonical_title: Mapped[str] = mapped_column(String(512), nullable=False)
    sort_title: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_artist_credit: Mapped[str] = mapped_column(String(512), nullable=False)
    sort_artist_credit: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_release_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("release.id"),
        nullable=True,
    )
    canonical_mix_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )

    canonical_release: Mapped[Release | None] = relationship(back_populates="tracks")
    aliases: Mapped[list["TrackAlias"]] = relationship(back_populates="track", cascade="all, delete-orphan")
    files: Mapped[list["TrackFile"]] = relationship(back_populates="track", cascade="all, delete-orphan")
    source_provenance: Mapped[list["SourceProvenance"]] = relationship(
        back_populates="track",
        cascade="all, delete-orphan",
    )


class TrackAlias(Base):
    __tablename__ = "track_alias"
    __table_args__ = (
        UniqueConstraint(
            "alias_type",
            "value",
            "provider",
            name="uq_track_alias_alias_provider",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("track.id"), nullable=False, index=True)
    alias_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(1024), nullable=False)
    provider: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    source: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[float | None] = mapped_column(Float())

    track: Mapped[Track] = relationship(back_populates="aliases")


class TrackFile(Base):
    __tablename__ = "track_file"
    __table_args__ = (
        CheckConstraint(
            "role IN ('archive_master', 'dj_derivative', 'device_export', 'sync_copy')",
            name="ck_track_file_role",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("track.id"), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    file_hash_sha256: Mapped[str | None] = mapped_column(String(64))
    acoustic_fingerprint: Mapped[str | None] = mapped_column(Text())
    format: Mapped[str | None] = mapped_column(String(64))
    bitrate: Mapped[int | None] = mapped_column(Integer())
    sample_rate: Mapped[int | None] = mapped_column(Integer())
    duration_ms: Mapped[int | None] = mapped_column(Integer())
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    derived_from_file_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("track_file.id"),
        nullable=True,
    )
    is_preferred: Mapped[bool] = mapped_column(Boolean(), default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean(), default=True, nullable=False)

    track: Mapped[Track] = relationship(back_populates="files", foreign_keys=[track_id])
    derived_from_file: Mapped["TrackFile | None"] = relationship(remote_side=[id])


class SourceProvenance(Base):
    __tablename__ = "source_provenance"
    __table_args__ = (
        UniqueConstraint(
            "track_id",
            "source_type",
            "source_key",
            name="uq_source_provenance_track_source_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("track.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_ref: Mapped[str | None] = mapped_column(String(2048))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    track: Mapped[Track] = relationship(back_populates="source_provenance")


class JobRun(Base):
    __tablename__ = "job_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(String(128), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean(), default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="job_run", cascade="all, delete-orphan")


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_run.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    job_run: Mapped[JobRun] = relationship(back_populates="audit_events")


class RawProviderResult(Base):
    __tablename__ = "raw_provider_result"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    batch_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255))
    query_text: Mapped[str] = mapped_column(String(1024), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MatchCandidate(Base):
    __tablename__ = "match_candidate"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    raw_result_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("raw_provider_result.id"),
        nullable=False,
        index=True,
    )
    track_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("track.id"),
        nullable=True,
        index=True,
    )
    score: Mapped[float] = mapped_column(Float(), nullable=False)
    reasons_json: Mapped[list[str]] = mapped_column(JSON(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")


class MetadataCandidate(Base):
    __tablename__ = "metadata_candidate"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    track_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("track.id"),
        nullable=True,
        index=True,
    )
    raw_result_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("raw_provider_result.id"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_value_json: Mapped[Any] = mapped_column(JSON(), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(), nullable=False)
    rationale_json: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    is_user_override: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)


class ApprovedMetadata(Base):
    __tablename__ = "approved_metadata"
    __table_args__ = (
        UniqueConstraint("track_id", "field_name", name="uq_approved_metadata_track_field"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("track.id"), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[Any] = mapped_column(JSON(), nullable=False)
    approved_from_candidate_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("metadata_candidate.id"),
        nullable=True,
        index=True,
    )
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    is_user_override: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)


class ExportWriteLog(Base):
    __tablename__ = "export_write_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_run.id"), nullable=False, index=True)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("track.id"), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(128), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    old_value_json: Mapped[Any | None] = mapped_column(JSON())
    new_value_json: Mapped[Any | None] = mapped_column(JSON())
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    written_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VocabTerm(Base):
    __tablename__ = "vocab_term"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    domain: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    canonical_value: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text())


class VocabAlias(Base):
    __tablename__ = "vocab_alias"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vocab_term_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("vocab_term.id"),
        nullable=False,
        index=True,
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(255))


class TrackVocabAssignment(Base):
    __tablename__ = "track_vocab_assignment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    track_id: Mapped[str] = mapped_column(String(36), ForeignKey("track.id"), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_value: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float] = mapped_column(Float(), nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
