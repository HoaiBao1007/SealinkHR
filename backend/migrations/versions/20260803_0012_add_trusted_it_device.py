"""Add trusted IT devices and device address audit fields.

Revision ID: 20260803_0012
Revises: 20260731_0011
Create Date: 2026-08-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260803_0012"
down_revision: Union[str, None] = "20260731_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trusted_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_label", sa.String(length=100), nullable=False),
        sa.Column("credential_hash", sa.String(length=64), nullable=True),
        sa.Column("enrollment_ip", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_hash"),
    )
    op.create_index("ix_trusted_devices_user_id", "trusted_devices", ["user_id"])
    op.create_index("ix_trusted_devices_user_active", "trusted_devices", ["user_id", "is_active"])
    op.add_column("system_audit_events", sa.Column("device_address", sa.String(length=100), nullable=True))
    op.add_column("attendance_overrides_audit", sa.Column("source_ip", sa.String(length=64), nullable=True))
    op.add_column("attendance_overrides_audit", sa.Column("device_address", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("attendance_overrides_audit", "device_address")
    op.drop_column("attendance_overrides_audit", "source_ip")
    op.drop_column("system_audit_events", "device_address")
    op.drop_index("ix_trusted_devices_user_active", table_name="trusted_devices")
    op.drop_index("ix_trusted_devices_user_id", table_name="trusted_devices")
    op.drop_table("trusted_devices")
