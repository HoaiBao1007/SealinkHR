"""Add employee contract type and date range.

Revision ID: 20260818_0023
Revises: 20260813_0022
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260818_0023"
down_revision: Union[str, None] = "20260813_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("contract_type", sa.String(length=30), nullable=True))
    op.add_column("employees", sa.Column("contract_sign_date", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("contract_start_date", sa.Date(), nullable=True))
    op.add_column("employees", sa.Column("contract_end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "contract_end_date")
    op.drop_column("employees", "contract_start_date")
    op.drop_column("employees", "contract_sign_date")
    op.drop_column("employees", "contract_type")
