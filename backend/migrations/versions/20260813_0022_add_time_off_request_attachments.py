"""Add private attachments for Time Off requests.

Revision ID: 20260813_0022
Revises: 20260813_0021
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_0022"
down_revision: Union[str, None] = "20260813_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This migration is additive only. Existing Time Off requests and their
    # data stay untouched.
    op.create_table(
        "off_request_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["off_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_filename"),
    )
    op.create_index("ix_off_request_attachments_request_id", "off_request_attachments", ["request_id"])
    op.create_index("ix_off_request_attachments_uploaded_by_user_id", "off_request_attachments", ["uploaded_by_user_id"])
    op.create_index("ix_off_request_attachments_created_at", "off_request_attachments", ["created_at"])
    op.create_index(
        "ix_off_request_attachments_staged_by",
        "off_request_attachments",
        ["uploaded_by_user_id", "request_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_off_request_attachments_staged_by", table_name="off_request_attachments")
    op.drop_index("ix_off_request_attachments_created_at", table_name="off_request_attachments")
    op.drop_index("ix_off_request_attachments_uploaded_by_user_id", table_name="off_request_attachments")
    op.drop_index("ix_off_request_attachments_request_id", table_name="off_request_attachments")
    op.drop_table("off_request_attachments")
