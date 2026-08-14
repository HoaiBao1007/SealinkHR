"""Add role-aware notifications and per-user read state.

Revision ID: 20260803_0013
Revises: 20260803_0012
Create Date: 2026-08-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260803_0013"
down_revision: Union[str, None] = "20260803_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
        sa.Column("action_url", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_category", "notifications", ["category"])
    op.create_index("ix_notifications_event_type", "notifications", ["event_type"])
    op.create_index("ix_notifications_target_user_id", "notifications", ["target_user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index("ix_notifications_created_category", "notifications", ["created_at", "category"])
    op.create_index("ix_notifications_target_created", "notifications", ["target_user_id", "created_at"])

    op.create_table(
        "notification_reads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", "user_id", name="uq_notification_reads_notification_user"),
    )
    op.create_index("ix_notification_reads_notification_id", "notification_reads", ["notification_id"])
    op.create_index("ix_notification_reads_user_id", "notification_reads", ["user_id"])
    op.create_index("ix_notification_reads_user_read", "notification_reads", ["user_id", "read_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_reads_user_read", table_name="notification_reads")
    op.drop_index("ix_notification_reads_user_id", table_name="notification_reads")
    op.drop_index("ix_notification_reads_notification_id", table_name="notification_reads")
    op.drop_table("notification_reads")
    op.drop_index("ix_notifications_target_created", table_name="notifications")
    op.drop_index("ix_notifications_created_category", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_target_user_id", table_name="notifications")
    op.drop_index("ix_notifications_event_type", table_name="notifications")
    op.drop_index("ix_notifications_category", table_name="notifications")
    op.drop_table("notifications")
