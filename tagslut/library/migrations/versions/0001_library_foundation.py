"""library foundation

Revision ID: 0001_library_foundation
Revises:
Create Date: 2026-03-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_library_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("artist_credit", sa.String(length=512), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("catalog_no", sa.String(length=255), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "job_run",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_type", sa.String(length=128), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "track",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("canonical_title", sa.String(length=512), nullable=False),
        sa.Column("sort_title", sa.String(length=512), nullable=False),
        sa.Column("canonical_artist_credit", sa.String(length=512), nullable=False),
        sa.Column("sort_artist_credit", sa.String(length=512), nullable=False),
        sa.Column("canonical_release_id", sa.String(length=36), nullable=True),
        sa.Column("canonical_mix_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'archived', 'rejected')", name="ck_track_status"),
        sa.ForeignKeyConstraint(["canonical_release_id"], ["release.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_run_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_run_id"], ["job_run.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_event_job_run_id", "audit_event", ["job_run_id"])

    op.create_table(
        "source_provenance",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("track_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_key", sa.String(length=255), nullable=False),
        sa.Column("payload_ref", sa.String(length=2048), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["track_id"], ["track.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "track_id",
            "source_type",
            "source_key",
            name="uq_source_provenance_track_source_key",
        ),
    )
    op.create_index("ix_source_provenance_track_id", "source_provenance", ["track_id"])

    op.create_table(
        "track_alias",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("track_id", sa.String(length=36), nullable=False),
        sa.Column("alias_type", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=1024), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["track_id"], ["track.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "alias_type",
            "value",
            "provider",
            name="uq_track_alias_alias_provider",
        ),
    )
    op.create_index("ix_track_alias_track_id", "track_alias", ["track_id"])

    op.create_table(
        "track_file",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("track_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.String(length=2048), nullable=False),
        sa.Column("file_hash_sha256", sa.String(length=64), nullable=True),
        sa.Column("acoustic_fingerprint", sa.Text(), nullable=True),
        sa.Column("format", sa.String(length=64), nullable=True),
        sa.Column("bitrate", sa.Integer(), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("derived_from_file_id", sa.String(length=36), nullable=True),
        sa.Column("is_preferred", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "role IN ('archive_master', 'dj_derivative', 'device_export', 'sync_copy')",
            name="ck_track_file_role",
        ),
        sa.ForeignKeyConstraint(["derived_from_file_id"], ["track_file.id"]),
        sa.ForeignKeyConstraint(["track_id"], ["track.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("path"),
    )
    op.create_index("ix_track_file_track_id", "track_file", ["track_id"])


def downgrade() -> None:
    op.drop_index("ix_track_file_track_id", table_name="track_file")
    op.drop_table("track_file")
    op.drop_index("ix_track_alias_track_id", table_name="track_alias")
    op.drop_table("track_alias")
    op.drop_index("ix_source_provenance_track_id", table_name="source_provenance")
    op.drop_table("source_provenance")
    op.drop_index("ix_audit_event_job_run_id", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_table("track")
    op.drop_table("job_run")
    op.drop_table("release")
