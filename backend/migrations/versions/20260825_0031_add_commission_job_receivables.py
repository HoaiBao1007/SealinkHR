"""Add private receivable attachments for commission JOBs.

Revision ID: 20260825_0031
Revises: 20260824_0030
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_0031"
down_revision: Union[str, None] = "20260824_0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Additive only: existing commission periods and JOB data remain intact.
    op.create_table(
        "commission_job_receivable_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("uploaded_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["commission_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["period_id"], ["commission_periods.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_filename"),
    )
    op.create_index("ix_commission_receivables_period_id", "commission_job_receivable_attachments", ["period_id"])
    op.create_index("ix_commission_receivables_job_id", "commission_job_receivable_attachments", ["job_id"])
    op.create_index("ix_commission_receivables_created_at", "commission_job_receivable_attachments", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_commission_receivables_created_at", table_name="commission_job_receivable_attachments")
    op.drop_index("ix_commission_receivables_job_id", table_name="commission_job_receivable_attachments")
    op.drop_index("ix_commission_receivables_period_id", table_name="commission_job_receivable_attachments")
    op.drop_table("commission_job_receivable_attachments")
