"""Use double precision for reconciled commission monetary values.

Revision ID: 20260825_0035
Revises: 20260825_0034
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_0035"
down_revision: Union[str, None] = "20260825_0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DOUBLE = sa.Float(precision=53)
FLOAT = sa.Float()


def upgrade() -> None:
    for column in (
        "hold_bonus_percent",
        "hold_bonus_amount",
        "receivable_amount",
        "balance_amount",
        "payment_received_amount",
    ):
        op.alter_column("commission_jobs", column, existing_type=FLOAT, type_=DOUBLE, existing_nullable=True)
    op.alter_column("commission_wallet_ledger", "amount", existing_type=FLOAT, type_=DOUBLE, existing_nullable=False)


def downgrade() -> None:
    op.alter_column("commission_wallet_ledger", "amount", existing_type=DOUBLE, type_=FLOAT, existing_nullable=False)
    for column in (
        "payment_received_amount",
        "balance_amount",
        "receivable_amount",
        "hold_bonus_amount",
        "hold_bonus_percent",
    ):
        op.alter_column("commission_jobs", column, existing_type=DOUBLE, type_=FLOAT, existing_nullable=True)
