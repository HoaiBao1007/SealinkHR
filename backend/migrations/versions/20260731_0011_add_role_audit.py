"""Add operational roles support and append-only system audit.

Revision ID: 20260731_0011
Revises: 20260730_0010
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260731_0011"
down_revision: Union[str, None] = "20260730_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_username", sa.String(length=100), nullable=False),
        sa.Column("actor_role", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("source_ip", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_audit_events_occurred_at", "system_audit_events", ["occurred_at"])
    op.create_index("ix_system_audit_events_actor_user_id", "system_audit_events", ["actor_user_id"])
    op.create_index("ix_system_audit_events_action", "system_audit_events", ["action"])
    op.create_index("ix_system_audit_events_resource_type", "system_audit_events", ["resource_type"])
    op.create_index("ix_system_audit_occurred_actor", "system_audit_events", ["occurred_at", "actor_user_id"])
    op.create_index("ix_system_audit_resource", "system_audit_events", ["resource_type", "resource_id"])


def downgrade() -> None:
    op.drop_index("ix_system_audit_resource", table_name="system_audit_events")
    op.drop_index("ix_system_audit_occurred_actor", table_name="system_audit_events")
    op.drop_index("ix_system_audit_events_resource_type", table_name="system_audit_events")
    op.drop_index("ix_system_audit_events_action", table_name="system_audit_events")
    op.drop_index("ix_system_audit_events_actor_user_id", table_name="system_audit_events")
    op.drop_index("ix_system_audit_events_occurred_at", table_name="system_audit_events")
    op.drop_table("system_audit_events")
