"""Link one stored commission receivable file to multiple JOBs.

Revision ID: 20260825_0032
Revises: 20260825_0031
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_0032"
down_revision: Union[str, None] = "20260825_0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Additive only. Existing files are retained and backfilled to their current JOB.
    op.create_table(
        "commission_job_receivable_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("attachment_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["attachment_id"], ["commission_job_receivable_attachments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["commission_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["period_id"], ["commission_periods.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "attachment_id", name="uq_commission_receivable_job_attachment"),
    )
    op.create_index("ix_commission_receivable_links_period_id", "commission_job_receivable_links", ["period_id"])
    op.create_index("ix_commission_receivable_links_job_id", "commission_job_receivable_links", ["job_id"])
    op.create_index("ix_commission_receivable_links_attachment_id", "commission_job_receivable_links", ["attachment_id"])
    op.execute(sa.text(
        "INSERT INTO commission_job_receivable_links (period_id, job_id, attachment_id) "
        "SELECT period_id, job_id, id FROM commission_job_receivable_attachments"
    ))


def downgrade() -> None:
    op.drop_index("ix_commission_receivable_links_attachment_id", table_name="commission_job_receivable_links")
    op.drop_index("ix_commission_receivable_links_job_id", table_name="commission_job_receivable_links")
    op.drop_index("ix_commission_receivable_links_period_id", table_name="commission_job_receivable_links")
    op.drop_table("commission_job_receivable_links")
