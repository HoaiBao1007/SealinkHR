"""Use double precision for all commission numeric values.

Revision ID: 20260826_0036
Revises: 20260825_0035
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260826_0036"
down_revision: Union[str, None] = "20260825_0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DOUBLE = sa.Float(precision=53)
FLOAT = sa.Float()


TABLE_COLUMNS = {
    "commission_jobs": (
        ("wt", True),
        ("vol", True),
        ("realized_revenue", False),
        ("unrealized_revenue", False),
        ("realized_cost", False),
        ("unrealized_cost", False),
        ("profit_loss", False),
    ),
    "commission_rep_overrides": (
        ("override_profit_loss", True),
        ("override_target", True),
        ("override_bonus_rate", True),
        ("override_total_bonus", True),
        ("override_monthly_bonus", True),
    ),
    "commission_payout_policies": (("minimum_amount", False),),
    "commission_calculation_snapshots": (
        ("monthly_bonus", False),
        ("total_bonus_quarter", False),
    ),
    "commission_bonus_entitlements": (("calculated_amount", False),),
    "commission_payout_schedules": (("total_amount", False),),
    "commission_payout_schedule_allocations": (("amount", False),),
}


def _change_numeric_type(source_type: sa.Float, target_type: sa.Float) -> None:
    for table_name, columns in TABLE_COLUMNS.items():
        for column_name, nullable in columns:
            op.alter_column(
                table_name,
                column_name,
                existing_type=source_type,
                type_=target_type,
                existing_nullable=nullable,
            )


def upgrade() -> None:
    _change_numeric_type(FLOAT, DOUBLE)


def downgrade() -> None:
    _change_numeric_type(DOUBLE, FLOAT)
