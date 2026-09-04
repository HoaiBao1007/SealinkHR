"""Store commission receivable reconciliation amounts on each JOB.

Revision ID: 20260825_0034
Revises: 20260825_0033
Create Date: 2026-08-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_0034"
down_revision: Union[str, None] = "20260825_0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Additive and nullable: existing P&L, wallet and receivable data is kept.
    op.add_column("commission_jobs", sa.Column("receivable_amount", sa.Float(), nullable=True))
    op.add_column("commission_jobs", sa.Column("balance_amount", sa.Float(), nullable=True))
    op.add_column("commission_jobs", sa.Column("payment_received_amount", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("commission_jobs", "payment_received_amount")
    op.drop_column("commission_jobs", "balance_amount")
    op.drop_column("commission_jobs", "receivable_amount")
