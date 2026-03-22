"""allow queued source provenance rows without linked tracks

Revision ID: 0003_source_provenance_queue
Revises: 0002_tagging_core
Create Date: 2026-03-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_source_provenance_queue"
down_revision = "0002_tagging_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("source_provenance") as batch_op:
        batch_op.alter_column(
            "track_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("source_provenance") as batch_op:
        batch_op.alter_column(
            "track_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
