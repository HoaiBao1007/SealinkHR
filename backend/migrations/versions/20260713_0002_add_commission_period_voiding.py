"""allow commission periods to be voided with wallet reversals

Revision ID: 20260713_0002
Revises: 20260713_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20260713_0002"
down_revision = "20260713_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commission_periods", sa.Column("is_voided", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("commission_periods", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("commission_periods", sa.Column("voided_by", sa.String(length=100), nullable=True))
    op.create_index("ix_commission_periods_is_voided", "commission_periods", ["is_voided"])


def downgrade() -> None:
    op.drop_index("ix_commission_periods_is_voided", table_name="commission_periods")
    op.drop_column("commission_periods", "voided_by")
    op.drop_column("commission_periods", "voided_at")
    op.drop_column("commission_periods", "is_voided")
