"""add accountant-approved payroll days to timesheets

Revision ID: 20260824_0030
Revises: 20260824_0029
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0030"
down_revision: Union[str, None] = "20260824_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "timesheets",
        sa.Column("total_payroll_days", sa.Numeric(5, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("timesheets", "total_payroll_days")
