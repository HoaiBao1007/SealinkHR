"""add timesheet leave balance snapshots

Revision ID: 20260823_0027
Revises: 20260821_0026
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260823_0027"
down_revision: Union[str, None] = "20260821_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "timesheets",
        sa.Column("previous_paid_leave_balance", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "timesheets",
        sa.Column("current_month_paid_leave_credit", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "timesheets",
        sa.Column("remaining_paid_leave_days", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("timesheets", "remaining_paid_leave_days")
    op.drop_column("timesheets", "current_month_paid_leave_credit")
    op.drop_column("timesheets", "previous_paid_leave_balance")
