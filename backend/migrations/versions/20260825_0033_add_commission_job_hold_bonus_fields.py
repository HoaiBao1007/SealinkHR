"""Add manual hold bonus fields to commission JOBs.

Revision ID: 20260825_0033
Revises: 20260825_0032
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_0033"
down_revision: Union[str, None] = "20260825_0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, additive columns: no existing commission data is rewritten.
    op.add_column("commission_jobs", sa.Column("hold_bonus_percent", sa.Float(), nullable=True))
    op.add_column("commission_jobs", sa.Column("hold_bonus_amount", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("commission_jobs", "hold_bonus_amount")
    op.drop_column("commission_jobs", "hold_bonus_percent")
