"""add working-day calendar override

Revision ID: 20260824_0029
Revises: 20260824_0028
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0029"
down_revision: Union[str, None] = "20260824_0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "holiday_settings",
        sa.Column("is_working_day", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("holiday_settings", "is_working_day")
