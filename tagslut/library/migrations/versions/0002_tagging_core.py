"""tagging core

Revision ID: 0002_tagging_core
Revises: 0001_library_foundation
Create Date: 2026-03-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_tagging_core"
down_revision = "0001_library_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_provider_result",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("query_text", sa.String(length=1024), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_raw_provider_result_batch_id", "raw_provider_result", ["batch_id"])

    op.create_table(
        "match_candidate",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("raw_result_id", sa.String(length=36), nullable=False),
        sa.Column("track_id", sa.String(length=36), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["raw_result_id"], ["raw_provider_result.id"]),
        sa.ForeignKeyConstraint(["track_id"], ["track.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_match_candidate_raw_result_id", "match_candidate", ["raw_result_id"])
    op.create_index("ix_match_candidate_track_id", "match_candidate", ["track_id"])

    op.create_table(
        "metadata_candidate",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("track_id", sa.String(length=36), nullable=True),
        sa.Column("raw_result_id", sa.String(length=36), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("normalized_value_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_user_override", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["raw_result_id"], ["raw_provider_result.id"]),
        sa.ForeignKeyConstraint(["track_id"], ["track.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metadata_candidate_raw_result_id", "metadata_candidate", ["raw_result_id"])
    op.create_index("ix_metadata_candidate_track_id", "metadata_candidate", ["track_id"])

    op.create_table(
        "approved_metadata",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("track_id", sa.String(length=36), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("approved_from_candidate_id", sa.String(length=36), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_user_override", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["approved_from_candidate_id"], ["metadata_candidate.id"]),
        sa.ForeignKeyConstraint(["track_id"], ["track.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("track_id", "field_name", name="uq_approved_metadata_track_field"),
    )
    op.create_index("ix_approved_metadata_track_id", "approved_metadata", ["track_id"])
    op.create_index(
        "ix_approved_metadata_approved_from_candidate_id",
        "approved_metadata",
        ["approved_from_candidate_id"],
    )

    op.create_table(
        "export_write_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("job_run_id", sa.String(length=36), nullable=False),
        sa.Column("track_id", sa.String(length=36), nullable=False),
        sa.Column("target", sa.String(length=128), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("old_value_json", sa.JSON(), nullable=True),
        sa.Column("new_value_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("written_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_run_id"], ["job_run.id"]),
        sa.ForeignKeyConstraint(["track_id"], ["track.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_write_log_job_run_id", "export_write_log", ["job_run_id"])
    op.create_index("ix_export_write_log_track_id", "export_write_log", ["track_id"])

    op.create_table(
        "vocab_term",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("domain", sa.String(length=128), nullable=False),
        sa.Column("canonical_value", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vocab_term_domain", "vocab_term", ["domain"])

    op.create_table(
        "vocab_alias",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vocab_term_id", sa.String(length=36), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["vocab_term_id"], ["vocab_term.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vocab_alias_vocab_term_id", "vocab_alias", ["vocab_term_id"])

    op.create_table(
        "track_vocab_assignment",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("track_id", sa.String(length=36), nullable=False),
        sa.Column("domain", sa.String(length=128), nullable=False),
        sa.Column("canonical_value", sa.String(length=255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("assigned_by", sa.String(length=255), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["track_id"], ["track.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_track_vocab_assignment_track_id", "track_vocab_assignment", ["track_id"])


def downgrade() -> None:
    op.drop_index("ix_track_vocab_assignment_track_id", table_name="track_vocab_assignment")
    op.drop_table("track_vocab_assignment")
    op.drop_index("ix_vocab_alias_vocab_term_id", table_name="vocab_alias")
    op.drop_table("vocab_alias")
    op.drop_index("ix_vocab_term_domain", table_name="vocab_term")
    op.drop_table("vocab_term")
    op.drop_index("ix_export_write_log_track_id", table_name="export_write_log")
    op.drop_index("ix_export_write_log_job_run_id", table_name="export_write_log")
    op.drop_table("export_write_log")
    op.drop_index("ix_approved_metadata_approved_from_candidate_id", table_name="approved_metadata")
    op.drop_index("ix_approved_metadata_track_id", table_name="approved_metadata")
    op.drop_table("approved_metadata")
    op.drop_index("ix_metadata_candidate_track_id", table_name="metadata_candidate")
    op.drop_index("ix_metadata_candidate_raw_result_id", table_name="metadata_candidate")
    op.drop_table("metadata_candidate")
    op.drop_index("ix_match_candidate_track_id", table_name="match_candidate")
    op.drop_index("ix_match_candidate_raw_result_id", table_name="match_candidate")
    op.drop_table("match_candidate")
    op.drop_index("ix_raw_provider_result_batch_id", table_name="raw_provider_result")
    op.drop_table("raw_provider_result")
